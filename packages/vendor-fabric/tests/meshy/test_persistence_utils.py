"""Targeted tests for meshy persistence spec-hashing utilities."""

from __future__ import annotations

import hashlib

from vendor_fabric.meshy.persistence.utils import canonicalize_spec, compute_spec_hash


# --- canonicalize_spec ---------------------------------------------------


class TestCanonicalizeSpec:
    def test_canonical_form_is_sorted_and_compact(self):
        result = canonicalize_spec({"b": 2, "a": 1})
        assert result == '{"a":1,"b":2}'

    def test_no_whitespace_in_output(self):
        result = canonicalize_spec({"key": "value", "nested": {"z": 1, "a": 2}})
        assert " " not in result
        assert "\n" not in result

    def test_nested_dicts_are_sorted(self):
        result = canonicalize_spec({"outer": {"z": 1, "a": 2}})
        assert result == '{"outer":{"a":2,"z":1}}'

    def test_key_order_independence(self):
        left = canonicalize_spec({"a": 1, "b": 2, "c": 3})
        right = canonicalize_spec({"c": 3, "a": 1, "b": 2})
        assert left == right

    def test_value_order_dependence_for_lists(self):
        left = canonicalize_spec({"items": [1, 2, 3]})
        right = canonicalize_spec({"items": [3, 2, 1]})
        assert left != right

    def test_empty_dict(self):
        assert canonicalize_spec({}) == "{}"

    def test_round_trips_via_json_loads(self):
        import json

        spec = {"b": [1, 2], "a": {"nested": True}, "c": "text"}
        result = canonicalize_spec(spec)
        assert json.loads(result) == spec


# --- compute_spec_hash ---------------------------------------------------


class TestComputeSpecHash:
    def test_returns_truncated_sha256_of_canonical_spec(self):
        spec = {"prompt": "sword", "art_style": "realistic"}
        expected_full = hashlib.sha256(canonicalize_spec(spec).encode("utf-8")).hexdigest()
        assert compute_spec_hash(spec, length=12) == expected_full[:12]

    def test_default_length_is_12(self):
        spec = {"a": 1}
        assert len(compute_spec_hash(spec)) == 12

    def test_custom_length(self):
        spec = {"a": 1}
        assert len(compute_spec_hash(spec, length=24)) == 24

    def test_deterministic_for_same_spec(self):
        spec = {"prompt": "shield", "mode": "preview"}
        assert compute_spec_hash(spec) == compute_spec_hash(spec)

    def test_different_for_different_specs(self):
        assert compute_spec_hash({"a": 1}) != compute_spec_hash({"a": 2})

    def test_order_independent(self):
        left = compute_spec_hash({"a": 1, "b": 2})
        right = compute_spec_hash({"b": 2, "a": 1})
        assert left == right

    def test_safe_for_filenames(self):
        spec = {"prompt": "test/special?chars"}
        result = compute_spec_hash(spec)
        assert all(c in "0123456789abcdef" for c in result)
