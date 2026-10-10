"""RAG layer: LangChain loaders + splitter -> embeddings -> FAISS."""

from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from langchain_community.document_loaders import DirectoryLoader, TextLoader
from langchain_community.vectorstores import FAISS
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter

TITLE = re.compile(r"^# (Runbook|Postmortem) ((?:RB|PM)-\d+): (.*)$", re.M)
STOP = {"the", "a", "an", "and", "or", "of", "to", "in", "on", "is", "are", "for", "with", "at"}


class HashingEmbeddings(Embeddings):
    """Offline, deterministic bag-of-words embeddings (hashing trick). Used in tests/CI so
    they need no model download. Real runs use sentence-transformers (see get_embeddings)."""

    def __init__(self, dim: int = 768):
        self.dim = dim

    def _embed(self, text: str) -> list[float]:
        v = np.zeros(self.dim)
        for tok in re.findall(r"[a-z0-9_]+", text.lower()):
            if tok in STOP:
                continue
            h = int(hashlib.md5(tok.encode()).hexdigest(), 16)
            v[h % self.dim] += 1.0 if (h >> 40) & 1 else -1.0
        n = np.linalg.norm(v)
        return (v / n if n else v).tolist()

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._embed(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._embed(text)


def get_embeddings(backend: str | None = None) -> Embeddings:
    backend = backend or os.getenv("EMBEDDINGS_BACKEND", "hf")
    if backend == "hashing":
        return HashingEmbeddings()
    from langchain_huggingface import HuggingFaceEmbeddings  # heavy import, so lazy

    return HuggingFaceEmbeddings(
        model_name=os.getenv("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2"),
        encode_kwargs={"normalize_embeddings": True},
    )


@dataclass
class Hit:
    doc_id: str
    title: str
    doc_type: str
    fault_id: str  # ground-truth tag, used ONLY for evaluation, never shown to the LLM
    text: str
    distance: float


def load_documents(data_dir: str | Path) -> list[Document]:
    docs: list[Document] = []
    for sub in ("runbooks", "postmortems"):
        loader = DirectoryLoader(
            str(Path(data_dir) / sub), glob="*.md", loader_cls=TextLoader,
            loader_kwargs={"encoding": "utf-8"},
        )
        for d in loader.load():
            m = TITLE.search(d.page_content)
            d.metadata.update(
                doc_type=m.group(1).lower(),
                doc_id=m.group(2),
                title=m.group(3),
                fault_id=Path(d.metadata["source"]).stem.split("__")[0],
            )
            docs.append(d)
    return docs


def chunk(docs: list[Document]) -> list[Document]:
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=700, chunk_overlap=80, separators=["\n## ", "\n\n", "\n", " "]
    )
    chunks = splitter.split_documents(docs)
    for c in chunks:  # keep the title in every chunk so it stays self-explanatory
        c.page_content = f"{c.metadata['doc_id']} {c.metadata['title']}\n{c.page_content}"
    return chunks


class RunbookRetriever:
    def __init__(self, store: FAISS):
        self.store = store

    @classmethod
    def build(cls, data_dir: str | Path, embeddings: Embeddings) -> RunbookRetriever:
        chunks = chunk(load_documents(data_dir))
        return cls(FAISS.from_documents(chunks, embeddings))

    def save(self, path: str | Path) -> None:
        self.store.save_local(str(path))

    @classmethod
    def load(cls, path: str | Path, embeddings: Embeddings) -> RunbookRetriever:
        # allow_dangerous_deserialization is fine here: we load an index we built ourselves
        return cls(FAISS.load_local(str(path), embeddings, allow_dangerous_deserialization=True))

    def search(self, query: str, k: int = 3) -> list[Hit]:
        """Top-k *distinct documents* (best chunk per document)."""
        seen, hits = set(), []
        for doc, dist in self.store.similarity_search_with_score(query, k=k * 4):
            if doc.metadata["doc_id"] in seen:
                continue
            seen.add(doc.metadata["doc_id"])
            md = doc.metadata
            hits.append(
                Hit(md["doc_id"], md["title"], md["doc_type"], md["fault_id"],
                    doc.page_content, float(dist))
            )
            if len(hits) == k:
                break
        return hits
