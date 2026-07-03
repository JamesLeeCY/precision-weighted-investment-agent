"""向量檢索封裝（規格第 4 節：MVP 用 ChromaDB）。

兩個實作共用同一介面：
- ChromaVectorStore：正式使用（需 `pip install chromadb`）
- SimpleVectorStore：純 numpy 的 hashing n-gram 向量 fallback，
  無外部依賴、可離線測試；中文檢索用字元 n-gram 足以應付 MVP 的
  「新聞太多時挑出最相關 k 則」用途

get_vector_store() 會優先嘗試 ChromaDB，失敗時自動退回 SimpleVectorStore。
"""
from __future__ import annotations

import hashlib
from abc import ABC, abstractmethod

import numpy as np


class BaseVectorStore(ABC):
    @abstractmethod
    def add(self, ids: list[str], texts: list[str], metadatas: list[dict] | None = None) -> None: ...

    @abstractmethod
    def query(self, text: str, k: int = 5) -> list[dict]:
        """回傳 [{id, text, score, metadata}]，score 越大越相關。"""


def _char_ngrams(text: str, n_min: int = 1, n_max: int = 3):
    text = "".join(text.split())
    for n in range(n_min, n_max + 1):
        for i in range(len(text) - n + 1):
            yield text[i : i + n]


def hashing_embed(text: str, dim: int = 512) -> np.ndarray:
    """確定性 hashing bag-of-ngrams 向量（無需模型下載）。"""
    vec = np.zeros(dim, dtype=np.float64)
    for gram in _char_ngrams(text):
        h = int(hashlib.md5(gram.encode("utf-8")).hexdigest(), 16)
        vec[h % dim] += 1.0 if (h >> 16) % 2 == 0 else -1.0
    norm = np.linalg.norm(vec)
    return vec / norm if norm > 0 else vec


class SimpleVectorStore(BaseVectorStore):
    def __init__(self, dim: int = 512):
        self.dim = dim
        self._ids: list[str] = []
        self._texts: list[str] = []
        self._metas: list[dict] = []
        self._matrix: np.ndarray | None = None

    def add(self, ids, texts, metadatas=None):
        metadatas = metadatas or [{} for _ in ids]
        vecs = np.stack([hashing_embed(t, self.dim) for t in texts])
        self._matrix = vecs if self._matrix is None else np.vstack([self._matrix, vecs])
        self._ids.extend(ids)
        self._texts.extend(texts)
        self._metas.extend(metadatas)

    def query(self, text, k=5):
        if self._matrix is None or not len(self._ids):
            return []
        q = hashing_embed(text, self.dim)
        scores = self._matrix @ q
        order = np.argsort(scores)[::-1][:k]
        return [
            {"id": self._ids[i], "text": self._texts[i], "score": float(scores[i]), "metadata": self._metas[i]}
            for i in order
        ]


class ChromaVectorStore(BaseVectorStore):
    def __init__(self, collection_name: str = "news", persist_dir: str | None = None):
        import chromadb  # 延遲載入：未安裝時不影響其餘模組

        client = chromadb.PersistentClient(path=persist_dir) if persist_dir else chromadb.Client()
        self.collection = client.get_or_create_collection(collection_name)

    def add(self, ids, texts, metadatas=None):
        self.collection.add(ids=ids, documents=texts, metadatas=metadatas)

    def query(self, text, k=5):
        res = self.collection.query(query_texts=[text], n_results=k)
        out = []
        for i, id_ in enumerate(res["ids"][0]):
            out.append(
                {
                    "id": id_,
                    "text": res["documents"][0][i],
                    # chroma 回傳 distance，轉為越大越相關
                    "score": -float(res["distances"][0][i]),
                    "metadata": (res["metadatas"][0][i] or {}),
                }
            )
        return out


def get_vector_store(prefer_chroma: bool = True, **kwargs) -> BaseVectorStore:
    if prefer_chroma:
        try:
            return ChromaVectorStore(**kwargs)
        except Exception:
            pass
    return SimpleVectorStore()
