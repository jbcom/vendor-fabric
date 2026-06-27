"""Tests for Meshy vector store persistence helpers."""

from __future__ import annotations

import sys

from types import ModuleType
from unittest.mock import patch

from extended_data.containers import ExtendedDict, ExtendedList, ExtendedString

from vendor_fabric.meshy.persistence import vector_store as vector_store_module
from vendor_fabric.meshy.persistence.vector_store import VectorStore, get_embedding


def test_record_generation_returns_extended_payload(temp_dir) -> None:
    """Recording a generation should expose an extended mapping payload."""
    with VectorStore(temp_dir / "assets.db") as store:
        result = store.record_generation(
            spec_hash="hash-abc",
            prompt="cute otter character",
            project="project1",
            task_id="task-123",
            metadata={"source": "test"},
        )

    assert isinstance(result, ExtendedDict)
    assert result["spec_hash"] == "hash-abc"
    assert result["prompt"] == "cute otter character"
    assert isinstance(result["prompt"], ExtendedString)
    assert isinstance(result["metadata"], ExtendedDict)
    assert result["metadata"]["source"] == "test"
    assert isinstance(result["created_at"], ExtendedString)


def test_record_generation_is_idempotent_with_extended_payload(temp_dir) -> None:
    """Duplicate spec hashes should return the existing extended payload."""
    with VectorStore(temp_dir / "assets.db") as store:
        first = store.record_generation(
            spec_hash="hash-abc",
            prompt="first prompt",
            project="project1",
        )
        second = store.record_generation(
            spec_hash="hash-abc",
            prompt="second prompt",
            project="project1",
        )

    assert isinstance(second, ExtendedDict)
    assert second["id"] == first["id"]
    assert second["prompt"] == "first prompt"


def test_get_record_methods_return_extended_payloads(temp_dir) -> None:
    """Spec hash and task ID lookups should return extended mapping payloads."""
    with VectorStore(temp_dir / "assets.db") as store:
        store.record_generation(
            spec_hash="hash-abc",
            prompt="cute otter character",
            project="project1",
            task_id="task-123",
        )

        by_hash = store.get_by_spec_hash("hash-abc")
        by_task = store.get_by_task_id("task-123")

    assert isinstance(by_hash, ExtendedDict)
    assert by_hash["spec_hash"] == "hash-abc"
    assert isinstance(by_task, ExtendedDict)
    assert by_task["task_id"] == "task-123"


def test_record_metadata_decodes_through_data_boundary(temp_dir, monkeypatch) -> None:
    """Persisted metadata should use the shared JSON decoder on reads."""
    with VectorStore(temp_dir / "assets.db") as store:
        store.record_generation(
            spec_hash="hash-abc",
            prompt="cute otter character",
            project="project1",
            metadata={"source": "test"},
        )

        def fail_local_json_loads(*_: object) -> object:
            raise AssertionError("metadata_json must be decoded through decode_file")

        monkeypatch.setattr(vector_store_module.json, "loads", fail_local_json_loads)
        record = store.get_by_spec_hash("hash-abc")

    assert isinstance(record, ExtendedDict)
    assert record["metadata"]["source"] == "test"


def test_record_metadata_encodes_through_export_boundary(temp_dir) -> None:
    """Persisted metadata should use the shared JSON export boundary on writes."""
    with VectorStore(temp_dir / "assets.db") as store:
        with patch(
            "vendor_fabric.meshy.persistence.vector_store.wrap_raw_data_for_export",
            wraps=vector_store_module.wrap_raw_data_for_export,
        ) as mock_wrap_for_export:
            store.record_generation(
                spec_hash="hash-abc",
                prompt="cute otter character",
                project="project1",
                metadata={"source": "test"},
            )

    mock_wrap_for_export.assert_called_once_with({"source": "test"}, allow_encoding="json")


def test_search_text_and_list_pending_return_extended_payloads(temp_dir) -> None:
    """Search and pending queries should return extended lists of mappings."""
    with VectorStore(temp_dir / "assets.db") as store:
        store.record_generation(
            spec_hash="hash-otter",
            prompt="cute otter character",
            project="project1",
        )
        store.record_generation(
            spec_hash="hash-badger",
            prompt="armored badger character",
            project="project2",
        )
        store.update_status("hash-badger", "SUCCEEDED")

        search_results = store.search_text("otter")
        pending_results = store.list_pending(project="project1")

    assert isinstance(search_results, ExtendedList)
    assert len(search_results) == 1
    assert isinstance(search_results[0], ExtendedDict)
    assert search_results[0]["spec_hash"] == "hash-otter"

    assert isinstance(pending_results, ExtendedList)
    assert len(pending_results) == 1
    assert isinstance(pending_results[0]["prompt"], ExtendedString)
    assert pending_results[0]["project"] == "project1"


def test_search_similar_without_vector_extension_returns_extended_list(temp_dir, monkeypatch) -> None:
    """The no-vector fallback should still expose an extended list."""
    monkeypatch.setattr(vector_store_module, "_HAS_VECTOR", False)

    with VectorStore(temp_dir / "assets.db") as store:
        result = store.search_similar([0.0] * store.embedding_dim)

    assert isinstance(result, ExtendedList)
    assert result == []


def test_get_embedding_returns_extended_vector(monkeypatch) -> None:
    """Embedding helper should promote vectors when the optional encoder exists."""

    class _FakeEmbedding:
        def tolist(self) -> list[float]:
            return [0.1, 0.2, 0.3]

    class _FakeEncoder:
        def encode(self, text: str) -> _FakeEmbedding:
            assert text == "cute otter"
            return _FakeEmbedding()

    module = ModuleType("sentence_transformers")
    module.SentenceTransformer = lambda model: _FakeEncoder()  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "sentence_transformers", module)

    result = get_embedding("cute otter")

    assert isinstance(result, ExtendedList)
    assert result == [0.1, 0.2, 0.3]
