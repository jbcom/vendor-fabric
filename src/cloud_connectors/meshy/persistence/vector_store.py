"""SQLite vector store for idempotency tracking and RAG embeddings.

This module provides a vector-enabled SQLite database for:
1. Idempotency tracking - deduplicate asset generation requests
2. RAG embeddings - semantic search over prompts, species, assets

Uses sqlite-vec for vector similarity search, falling back to
standard SQLite if vectors aren't needed.

Usage:
    from cloud_connectors.meshy.persistence.vector_store import VectorStore

    store = VectorStore("assets.db")

    # Track asset generation
    store.record_generation(
        spec_hash="abc123",
        prompt="cute otter character",
        task_id="meshy-task-id",
        embedding=get_embedding("cute otter character"),
    )

    # Find similar prompts (RAG)
    similar = store.search_similar("river otter", limit=5)

    # Check idempotency
    existing = store.get_by_spec_hash("abc123")

Requirements:
    pip install "cloud-connectors[meshy,vector]"

    The vector extra includes:
    - sqlite-vec (vector similarity extension)

    get_embedding() uses sentence-transformers only when users install it
    independently after reviewing its torch dependency tree.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3

from contextlib import contextmanager, suppress
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Self, cast

from extended_data.containers import ExtendedDict, ExtendedList, extend_data
from extended_data.io import wrap_raw_data_for_export
from extended_data.io.files import decode_file
from extended_data.primitives.formats.errors import DataDecodeError


if TYPE_CHECKING:
    from collections.abc import Iterator
    from types import TracebackType

# Vector extension is optional
_HAS_VECTOR = False
try:
    import sqlite_vec

    _HAS_VECTOR = True
except ImportError:
    pass


def _utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass
class GenerationRecord:
    """Record of a 3D asset generation."""

    id: int | None = None
    spec_hash: str = ""
    project: str = ""
    prompt: str = ""
    art_style: str = "sculpture"
    task_id: str | None = None
    status: str = "pending"
    model_url: str | None = None
    embedding: list[float] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=_utc_now)
    updated_at: datetime = field(default_factory=_utc_now)


@dataclass
class SimilarityResult:
    """Result from similarity search."""

    record: GenerationRecord
    distance: float
    score: float  # 1 - distance (higher = more similar)


def _record_payload(record: GenerationRecord) -> dict[str, Any]:
    """Convert an internal generation record to a JSON-friendly payload."""
    payload = asdict(record)
    payload["created_at"] = record.created_at.isoformat()
    payload["updated_at"] = record.updated_at.isoformat()
    return payload


def _similarity_payload(result: SimilarityResult) -> dict[str, Any]:
    """Convert an internal similarity result to a JSON-friendly payload."""
    return {
        "record": _record_payload(result.record),
        "distance": result.distance,
        "score": result.score,
    }


class VectorStore:
    """SQLite vector store for asset generation tracking and RAG.

    Features:
    - Idempotent task tracking by spec_hash
    - Vector similarity search for RAG
    - Full-text search fallback when vectors unavailable
    - Atomic transactions

    Args:
        db_path: Path to SQLite database file
        embedding_dim: Dimension of embedding vectors (default: 384 for MiniLM)
    """

    DEFAULT_EMBEDDING_DIM = 384  # sentence-transformers/all-MiniLM-L6-v2

    def __init__(
        self,
        db_path: str | Path = "cloud_connectors.meshy.db",
        embedding_dim: int = DEFAULT_EMBEDDING_DIM,
    ):
        self.db_path = Path(db_path)
        self.embedding_dim = embedding_dim
        self._conn: sqlite3.Connection | None = None
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        """Get or create database connection."""
        if self._conn is None:
            self._conn = sqlite3.connect(
                self.db_path,
                check_same_thread=False,
                isolation_level=None,  # Auto-commit mode
            )
            self._conn.row_factory = sqlite3.Row

            # Load vector extension if available
            if _HAS_VECTOR:
                self._conn.enable_load_extension(True)
                sqlite_vec.load(self._conn)

        return self._conn

    @contextmanager
    def _transaction(self) -> Iterator[sqlite3.Connection]:
        """Context manager for transactions."""
        conn = self._get_conn()
        conn.execute("BEGIN")
        try:
            yield conn
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise

    def _init_db(self) -> None:
        """Initialize database schema."""
        conn = self._get_conn()

        # Main generations table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS generations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                spec_hash TEXT UNIQUE NOT NULL,
                project TEXT NOT NULL DEFAULT 'default',
                prompt TEXT NOT NULL,
                art_style TEXT NOT NULL DEFAULT 'sculpture',
                task_id TEXT,
                status TEXT NOT NULL DEFAULT 'pending',
                model_url TEXT,
                metadata_json TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)

        # Indexes for common queries
        conn.execute("CREATE INDEX IF NOT EXISTS idx_generations_project ON generations(project)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_generations_task_id ON generations(task_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_generations_status ON generations(status)")

        # Full-text search for prompt content (fallback when no vectors)
        conn.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS generations_fts USING fts5(
                prompt,
                content='generations',
                content_rowid='id'
            )
        """)

        # Vector table for embeddings (if extension available)
        if _HAS_VECTOR:
            conn.execute(f"""
                CREATE VIRTUAL TABLE IF NOT EXISTS generation_embeddings USING vec0(
                    id INTEGER PRIMARY KEY,
                    embedding FLOAT[{self.embedding_dim}]
                )
            """)

        # Triggers to keep FTS in sync
        conn.execute("""
            CREATE TRIGGER IF NOT EXISTS generations_ai AFTER INSERT ON generations BEGIN
                INSERT INTO generations_fts(rowid, prompt) VALUES (new.id, new.prompt);
            END
        """)
        conn.execute("""
            CREATE TRIGGER IF NOT EXISTS generations_ad AFTER DELETE ON generations BEGIN
                DELETE FROM generations_fts WHERE rowid = old.id;
            END
        """)
        conn.execute("""
            CREATE TRIGGER IF NOT EXISTS generations_au AFTER UPDATE ON generations BEGIN
                DELETE FROM generations_fts WHERE rowid = old.id;
                INSERT INTO generations_fts(rowid, prompt) VALUES (new.id, new.prompt);
            END
        """)

    def record_generation(
        self,
        spec_hash: str,
        prompt: str,
        project: str = "default",
        art_style: str = "sculpture",
        task_id: str | None = None,
        embedding: list[float] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ExtendedDict:
        """Record a new generation (idempotent by spec_hash).

        If a record with the same spec_hash exists, returns existing.

        Args:
            spec_hash: Unique hash of the generation spec
            prompt: Text prompt for generation
            project: Project identifier
            art_style: Art style (realistic, sculpture, etc.)
            task_id: Meshy task ID if already submitted
            embedding: Optional embedding vector for RAG
            metadata: Additional metadata dict

        Returns:
            Extended generation record payload (existing or newly created)
        """
        now = _utc_now().isoformat()

        with self._transaction() as conn:
            # Check for existing (idempotency)
            cursor = conn.execute("SELECT * FROM generations WHERE spec_hash = ?", (spec_hash,))
            row = cursor.fetchone()

            if row:
                return cast(ExtendedDict, extend_data(_record_payload(self._row_to_record(row))))

            # Insert new record
            metadata_json = wrap_raw_data_for_export(metadata, allow_encoding="json") if metadata else None

            cursor = conn.execute(
                """
                INSERT INTO generations
                (spec_hash, project, prompt, art_style, task_id, status,
                 metadata_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, 'pending', ?, ?, ?)
            """,
                (spec_hash, project, prompt, art_style, task_id, metadata_json, now, now),
            )

            record_id = cursor.lastrowid

            # Store embedding if provided and vectors available
            if embedding and _HAS_VECTOR and len(embedding) == self.embedding_dim:
                embedding_blob = self._serialize_embedding(embedding)
                conn.execute(
                    "INSERT INTO generation_embeddings (id, embedding) VALUES (?, ?)",
                    (record_id, embedding_blob),
                )

            record = GenerationRecord(
                id=record_id,
                spec_hash=spec_hash,
                project=project,
                prompt=prompt,
                art_style=art_style,
                task_id=task_id,
                status="pending",
                embedding=embedding,
                metadata=metadata or {},
                created_at=datetime.fromisoformat(now),
                updated_at=datetime.fromisoformat(now),
            )
            return cast(ExtendedDict, extend_data(_record_payload(record)))

    def update_status(
        self,
        spec_hash: str,
        status: str,
        task_id: str | None = None,
        model_url: str | None = None,
    ) -> bool:
        """Update generation status.

        Args:
            spec_hash: Generation spec hash
            status: New status
            task_id: Optional task ID to update
            model_url: Optional model URL to update

        Returns:
            True if record was updated, False if not found
        """
        now = _utc_now().isoformat()

        with self._transaction() as conn:
            updates = ["status = ?", "updated_at = ?"]
            params: list[Any] = [status, now]

            if task_id is not None:
                updates.append("task_id = ?")
                params.append(task_id)

            if model_url is not None:
                updates.append("model_url = ?")
                params.append(model_url)

            params.append(spec_hash)

            cursor = conn.execute(
                f"UPDATE generations SET {', '.join(updates)} WHERE spec_hash = ?",  # noqa: S608
                params,
            )

            return cursor.rowcount > 0

    def get_by_spec_hash(self, spec_hash: str) -> ExtendedDict | None:
        """Get generation record by spec hash.

        Args:
            spec_hash: Generation spec hash

        Returns:
            Extended generation record payload or None
        """
        conn = self._get_conn()
        cursor = conn.execute("SELECT * FROM generations WHERE spec_hash = ?", (spec_hash,))
        row = cursor.fetchone()
        if not row:
            return None
        return cast(ExtendedDict, extend_data(_record_payload(self._row_to_record(row))))

    def get_by_task_id(self, task_id: str) -> ExtendedDict | None:
        """Get generation record by Meshy task ID.

        Args:
            task_id: Meshy task ID

        Returns:
            Extended generation record payload or None
        """
        conn = self._get_conn()
        cursor = conn.execute("SELECT * FROM generations WHERE task_id = ?", (task_id,))
        row = cursor.fetchone()
        if not row:
            return None
        return cast(ExtendedDict, extend_data(_record_payload(self._row_to_record(row))))

    def search_similar(
        self,
        query_embedding: list[float],
        limit: int = 10,
        project: str | None = None,
    ) -> ExtendedList[ExtendedDict]:
        """Search for similar generations using vector similarity.

        Args:
            query_embedding: Query embedding vector
            limit: Maximum results to return
            project: Optional project filter

        Returns:
            Extended similarity result payloads ordered by similarity (highest first)
        """
        if not _HAS_VECTOR:
            return cast(ExtendedList[ExtendedDict], extend_data([]))

        conn = self._get_conn()
        query_blob = self._serialize_embedding(query_embedding)

        if project:
            cursor = conn.execute(
                """
                SELECT g.*, e.distance
                FROM generation_embeddings e
                JOIN generations g ON g.id = e.id
                WHERE g.project = ?
                ORDER BY e.embedding <-> ?
                LIMIT ?
            """,
                (project, query_blob, limit),
            )
        else:
            cursor = conn.execute(
                """
                SELECT g.*, e.distance
                FROM generation_embeddings e
                JOIN generations g ON g.id = e.id
                ORDER BY e.embedding <-> ?
                LIMIT ?
            """,
                (query_blob, limit),
            )

        results: list[dict[str, Any]] = []
        for row in cursor:
            record = self._row_to_record(row)
            distance = row["distance"]
            results.append(
                _similarity_payload(
                    SimilarityResult(
                        record=record,
                        distance=distance,
                        score=1.0 - min(distance, 1.0),
                    )
                )
            )

        return cast(ExtendedList[ExtendedDict], extend_data(results))

    def search_text(
        self,
        query: str,
        limit: int = 10,
        project: str | None = None,
    ) -> ExtendedList[ExtendedDict]:
        """Full-text search for prompts.

        Falls back to this when vector search is unavailable.

        Args:
            query: Search query
            limit: Maximum results
            project: Optional project filter

        Returns:
            Extended generation record payloads
        """
        conn = self._get_conn()

        if project:
            cursor = conn.execute(
                """
                SELECT g.*
                FROM generations g
                JOIN generations_fts fts ON fts.rowid = g.id
                WHERE generations_fts MATCH ? AND g.project = ?
                LIMIT ?
            """,
                (query, project, limit),
            )
        else:
            cursor = conn.execute(
                """
                SELECT g.*
                FROM generations g
                JOIN generations_fts fts ON fts.rowid = g.id
                WHERE generations_fts MATCH ?
                LIMIT ?
            """,
                (query, limit),
            )

        return cast(
            ExtendedList[ExtendedDict],
            extend_data([_record_payload(self._row_to_record(row)) for row in cursor]),
        )

    def list_pending(self, project: str | None = None) -> ExtendedList[ExtendedDict]:
        """List all pending/in-progress generations.

        Args:
            project: Optional project filter

        Returns:
            Extended pending generation record payloads
        """
        conn = self._get_conn()

        if project:
            cursor = conn.execute(
                "SELECT * FROM generations WHERE status IN ('pending', 'in_progress') AND project = ?",
                (project,),
            )
        else:
            cursor = conn.execute("SELECT * FROM generations WHERE status IN ('pending', 'in_progress')")

        return cast(
            ExtendedList[ExtendedDict],
            extend_data([_record_payload(self._row_to_record(row)) for row in cursor]),
        )

    def compute_spec_hash(self, spec: dict[str, Any]) -> str:
        """Compute deterministic hash for a generation spec.

        Args:
            spec: Generation specification dict

        Returns:
            SHA256 hex digest
        """
        # Canonicalize JSON (sorted keys, no whitespace)
        canonical = json.dumps(spec, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode()).hexdigest()[:16]

    def _row_to_record(self, row: sqlite3.Row) -> GenerationRecord:
        """Convert database row to GenerationRecord."""
        metadata = {}
        if row["metadata_json"]:
            with suppress(DataDecodeError):
                metadata = decode_file(row["metadata_json"], suffix="json", as_extended=False)

        return GenerationRecord(
            id=row["id"],
            spec_hash=row["spec_hash"],
            project=row["project"],
            prompt=row["prompt"],
            art_style=row["art_style"],
            task_id=row["task_id"],
            status=row["status"],
            model_url=row["model_url"],
            metadata=metadata,
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )

    def _serialize_embedding(self, embedding: list[float]) -> bytes:
        """Serialize embedding to bytes for SQLite vec."""
        import struct

        return struct.pack(f"{len(embedding)}f", *embedding)

    def close(self) -> None:
        """Close database connection."""
        if self._conn:
            self._conn.close()
            self._conn = None

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        self.close()


# Convenience function for getting embeddings
def get_embedding(text: str, model: str = "all-MiniLM-L6-v2") -> ExtendedList[float] | None:
    """Get embedding for text using sentence-transformers.

    Args:
        text: Text to embed
        model: Model name (default: all-MiniLM-L6-v2)

    Returns:
        Extended embedding vector or None if sentence-transformers not available
    """
    try:
        from sentence_transformers import SentenceTransformer

        encoder = SentenceTransformer(model)
        embedding = encoder.encode(text)
        return cast(ExtendedList[float], extend_data(embedding.tolist()))
    except ImportError:
        return None
