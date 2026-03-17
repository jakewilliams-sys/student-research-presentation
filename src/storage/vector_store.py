"""
ChromaDB vector store for semantic search across research data.

Handles chunking, embedding, and retrieval of interview transcripts,
researcher notes, and other text documents. Uses ChromaDB's built-in
sentence-transformer embedding for zero-config setup.
"""

from __future__ import annotations

import hashlib
import logging
import re
from pathlib import Path
from typing import Any

import chromadb
from chromadb.config import Settings

from config.settings import (
    CHROMA_COLLECTION_NAME,
    CHROMA_PERSIST_DIR,
    CHUNK_OVERLAP,
    CHUNK_SIZE,
)

logger = logging.getLogger(__name__)


class VectorStore:
    """Semantic search over research documents using ChromaDB."""

    def __init__(self, persist_dir: str | None = None, collection_name: str | None = None):
        self._persist_dir = persist_dir or CHROMA_PERSIST_DIR
        self._collection_name = collection_name or CHROMA_COLLECTION_NAME

        Path(self._persist_dir).mkdir(parents=True, exist_ok=True)

        self._client = chromadb.PersistentClient(
            path=self._persist_dir,
            settings=Settings(anonymized_telemetry=False),
        )
        self._collection = self._client.get_or_create_collection(
            name=self._collection_name,
            metadata={"hnsw:space": "cosine"},
        )
        logger.info(
            "VectorStore ready: %d documents in '%s'",
            self._collection.count(),
            self._collection_name,
        )

    @property
    def count(self) -> int:
        return self._collection.count()

    # ------------------------------------------------------------------
    # Ingestion
    # ------------------------------------------------------------------

    def add_document(
        self,
        doc_id: str,
        text: str,
        metadata: dict[str, Any] | None = None,
        chunk_size: int | None = None,
        chunk_overlap: int | None = None,
    ) -> int:
        """
        Chunk and embed a document into the vector store.

        Returns the number of chunks created.
        """
        cs = chunk_size or CHUNK_SIZE
        co = chunk_overlap or CHUNK_OVERLAP
        base_meta = metadata or {}

        chunks = _chunk_text(text, cs, co)
        if not chunks:
            logger.warning("No chunks produced for document %s", doc_id)
            return 0

        ids = []
        documents = []
        metadatas = []

        for i, chunk in enumerate(chunks):
            chunk_id = f"{doc_id}__chunk_{i:04d}"
            chunk_meta = {
                **base_meta,
                "doc_id": doc_id,
                "chunk_index": i,
                "total_chunks": len(chunks),
            }
            # ChromaDB metadata values must be str, int, float, or bool
            chunk_meta = {k: v for k, v in chunk_meta.items() if isinstance(v, (str, int, float, bool))}

            ids.append(chunk_id)
            documents.append(chunk)
            metadatas.append(chunk_meta)

        self._collection.upsert(ids=ids, documents=documents, metadatas=metadatas)
        logger.info("Added %d chunks for document %s", len(chunks), doc_id)
        return len(chunks)

    def add_segments(self, segments: list[dict[str, Any]]) -> int:
        """
        Add pre-segmented data (e.g. coded interview segments) to the store.

        Each segment dict must have at least 'segment_id' and 'text'.
        """
        if not segments:
            return 0

        ids = []
        documents = []
        metadatas = []

        for seg in segments:
            seg_id = seg.get("segment_id", hashlib.md5(seg.get("text", "").encode()).hexdigest())
            meta = {
                k: v for k, v in seg.items()
                if k != "text" and isinstance(v, (str, int, float, bool))
            }
            ids.append(seg_id)
            documents.append(seg["text"])
            metadatas.append(meta)

        self._collection.upsert(ids=ids, documents=documents, metadatas=metadatas)
        logger.info("Added %d segments to vector store", len(segments))
        return len(segments)

    # ------------------------------------------------------------------
    # Retrieval
    # ------------------------------------------------------------------

    def search(
        self,
        query: str,
        n_results: int = 10,
        filters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """
        Semantic search across all documents.

        Returns list of dicts with 'id', 'text', 'metadata', 'distance'.
        """
        where = filters if filters else None

        results = self._collection.query(
            query_texts=[query],
            n_results=n_results,
            where=where,
        )

        hits: list[dict[str, Any]] = []
        if results and results["ids"]:
            for i, doc_id in enumerate(results["ids"][0]):
                hits.append({
                    "id": doc_id,
                    "text": results["documents"][0][i] if results["documents"] else "",
                    "metadata": results["metadatas"][0][i] if results["metadatas"] else {},
                    "distance": results["distances"][0][i] if results["distances"] else None,
                })

        return hits

    def get_participant_documents(
        self, participant_id: str, n_results: int = 100
    ) -> list[dict[str, Any]]:
        """Retrieve all stored documents for a specific participant."""
        return self.search(
            query="",
            n_results=n_results,
            filters={"participant_id": participant_id},
        )

    def get_by_doc_id(self, doc_id: str) -> list[dict[str, Any]]:
        """Retrieve all chunks for a specific document ID."""
        results = self._collection.get(
            where={"doc_id": doc_id},
            include=["documents", "metadatas"],
        )
        hits: list[dict[str, Any]] = []
        if results and results["ids"]:
            for i, cid in enumerate(results["ids"]):
                hits.append({
                    "id": cid,
                    "text": results["documents"][i] if results["documents"] else "",
                    "metadata": results["metadatas"][i] if results["metadatas"] else {},
                })
        return hits

    # ------------------------------------------------------------------
    # Management
    # ------------------------------------------------------------------

    def delete_document(self, doc_id: str) -> None:
        """Remove all chunks for a document."""
        existing = self._collection.get(where={"doc_id": doc_id})
        if existing and existing["ids"]:
            self._collection.delete(ids=existing["ids"])
            logger.info("Deleted %d chunks for document %s", len(existing["ids"]), doc_id)

    def reset(self) -> None:
        """Delete and recreate the collection."""
        self._client.delete_collection(self._collection_name)
        self._collection = self._client.get_or_create_collection(
            name=self._collection_name,
            metadata={"hnsw:space": "cosine"},
        )
        logger.info("Vector store reset")


# ---------------------------------------------------------------------------
# Text chunking
# ---------------------------------------------------------------------------

def _chunk_text(text: str, chunk_size: int, overlap: int) -> list[str]:
    """
    Split text into overlapping chunks, breaking at paragraph or sentence
    boundaries where possible.
    """
    if not text or not text.strip():
        return []

    paragraphs = re.split(r"\n\s*\n", text.strip())

    chunks: list[str] = []
    current_chunk: list[str] = []
    current_len = 0

    for para in paragraphs:
        para = para.strip()
        if not para:
            continue

        para_len = len(para)

        if current_len + para_len > chunk_size and current_chunk:
            chunks.append("\n\n".join(current_chunk))

            # Keep overlap from the end of the current chunk
            overlap_text = "\n\n".join(current_chunk)
            if len(overlap_text) > overlap:
                overlap_text = overlap_text[-overlap:]
            current_chunk = [overlap_text]
            current_len = len(overlap_text)

        current_chunk.append(para)
        current_len += para_len

    if current_chunk:
        chunks.append("\n\n".join(current_chunk))

    return chunks
