"""知识检索 — 混合检索：关键词 + 向量 → RRF 融合 → top-4"""

import os, re
from pathlib import Path
import numpy as np
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from langchain_core.runnables import RunnableConfig
from ..core.state import AgentState

_CACHE_DIR = Path(__file__).resolve().parent.parent / "knowledge_base" / ".cache"

# ---- 停用词 ----
_STOP_WORDS: set[str] = {
    "的", "了", "在", "是", "我", "有", "和", "就", "不", "人", "都", "一",
    "一个", "上", "也", "很", "到", "说", "要", "去", "你", "会", "着",
    "没有", "看", "好", "自己", "这", "他", "她", "它", "们", "那", "些",
    "什么", "怎么", "如何", "哪个", "可以", "这个", "那个", "如果", "因为",
    "所以", "但是", "而且", "或者", "然后", "虽然", "不过", "进行", "需要",
    "应该", "能够", "可能", "已经", "比如", "例如", "其中", "其他", "以及",
    "请", "对", "从", "把", "被", "让", "向", "往", "用", "以", "为",
    "与", "给", "等", "之", "中", "里", "外", "还", "更", "最", "只",
    "做", "作", "来", "去", "出", "到", "使", "将", "通过", "根据",
    "按照", "关于",
}


class HybridRetriever:
    """混合检索器：关键词 + 向量 → RRF 融合 → top-4。

    持有文档存储和 embedding 缓存，替代原来的模块级全局状态。
    """

    def __init__(self) -> None:
        self._doc_store: dict[str, list[Document]] = {}
        self._embeddings: dict[str, np.ndarray] = {}

    # ================================================================
    # embedding 工厂
    # ================================================================
    @staticmethod
    def _make_embedding() -> Embeddings:
        provider = os.environ.get("EMBEDDING_PROVIDER", "dashscope")
        model_name = os.environ.get("EMBEDDING_MODEL", "")
        if provider == "dashscope":
            from langchain_community.embeddings import DashScopeEmbeddings
            return DashScopeEmbeddings(
                model=model_name or "text-embedding-v1",
                dashscope_api_key=os.environ.get("DASHSCOPE_API_KEY"),
            )
        elif provider == "openai":
            from langchain_openai import OpenAIEmbeddings
            return OpenAIEmbeddings(model=model_name or "text-embedding-3-small")
        raise ValueError(f"不支持的 embedding provider: {provider}")

    # ================================================================
    # 文档存储
    # ================================================================
    def get_store(self, user_id: str = "default") -> list[Document]:
        if user_id not in self._doc_store:
            self._doc_store[user_id] = []
        return self._doc_store[user_id]

    # ================================================================
    # embedding 缓存
    # ================================================================
    @staticmethod
    def _cache_path(user_id: str) -> Path:
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        return _CACHE_DIR / f"{user_id}_embeddings.npz"

    @staticmethod
    def _load_embeddings(user_id: str) -> np.ndarray | None:
        path = HybridRetriever._cache_path(user_id)
        if not path.exists():
            return None
        try:
            return np.load(path)["embeddings"]
        except Exception:
            return None

    @staticmethod
    def _save_embeddings(user_id: str, emb: np.ndarray) -> None:
        np.savez_compressed(HybridRetriever._cache_path(user_id), embeddings=emb)

    async def _compute_embeddings(self, docs: list[Document]) -> np.ndarray:
        embedder = self._make_embedding()
        texts = [d.page_content for d in docs]
        all_vecs: list[list[float]] = []
        for i in range(0, len(texts), 20):
            batch = texts[i : i + 20]
            all_vecs.extend(await embedder.aembed_documents(batch))
            print(f"  [embedding] {min(i + 20, len(texts))}/{len(texts)}")
        return np.array(all_vecs, dtype=np.float32)

    async def ensure_embeddings(self, user_id: str = "default") -> np.ndarray:
        if user_id in self._embeddings:
            return self._embeddings[user_id]
        docs = self.get_store(user_id)
        if not docs:
            self._embeddings[user_id] = np.array([], dtype=np.float32)
            return self._embeddings[user_id]
        cached = self._load_embeddings(user_id)
        if cached is not None and cached.shape[0] == len(docs):
            print(f"  [缓存命中] 从磁盘加载了 {len(docs)} 条 embedding")
            self._embeddings[user_id] = cached
            return cached
        print(
            f"  [首次计算] 正在为 {len(docs)} 个文本块生成 embedding（仅此一次）..."
        )
        emb = await self._compute_embeddings(docs)
        self._save_embeddings(user_id, emb)
        self._embeddings[user_id] = emb
        print("  [缓存已保存] embedding 已持久化")
        return emb

    # ================================================================
    # 关键词提取
    # ================================================================
    @staticmethod
    def _extract_keywords(text: str) -> list[str]:
        c = re.findall(r'[一-鿿]{2,4}', text)
        e = re.findall(r'[a-zA-Z0-9_\-]{2,}', text)
        return [w for w in c if w not in _STOP_WORDS] + e

    # ================================================================
    # 检索
    # ================================================================
    @staticmethod
    def _keyword_search(
        query: str, docs: list[Document], top_k: int = 20
    ) -> list[tuple[float, int]]:
        keywords = HybridRetriever._extract_keywords(query)
        if not keywords:
            return []
        scored: list[tuple[float, int]] = []
        for idx, doc in enumerate(docs):
            content = doc.page_content
            score = sum(content.count(kw) for kw in keywords)
            if score > 0:
                scored.append((score / (len(content) + 1) * 10000, idx))
        scored.sort(key=lambda x: x[0], reverse=True)
        return scored[:top_k]

    async def _vector_search(
        self, query: str, embeddings: np.ndarray, top_k: int = 20
    ) -> list[tuple[float, int]]:
        if embeddings.size == 0:
            return []
        embedder = self._make_embedding()
        q = np.array(await embedder.aembed_query(query), dtype=np.float32)
        q = q / (np.linalg.norm(q) + 1e-8)
        d = embeddings / (np.linalg.norm(embeddings, axis=1, keepdims=True) + 1e-8)
        sims = np.dot(d, q)
        idx = np.argsort(sims)[::-1][:top_k]
        return [(float(sims[i]), int(i)) for i in idx if sims[i] > 0]

    @staticmethod
    def _rrf_fusion(
        kw: list[tuple[float, int]],
        vec: list[tuple[float, int]],
        k: int = 60,
    ) -> list[int]:
        scores: dict[int, float] = {}
        for rank, (_, idx) in enumerate(kw):
            scores[idx] = scores.get(idx, 0) + 1.0 / (k + rank + 1)
        for rank, (_, idx) in enumerate(vec):
            scores[idx] = scores.get(idx, 0) + 1.0 / (k + rank + 1)
        return [i for i, _ in sorted(scores.items(), key=lambda x: x[1], reverse=True)]

    # ================================================================
    # 分库检索（按 kb_code 过滤文档）
    # ================================================================
    def _filter_by_kb_codes(
        self, docs: list[Document], kb_codes: list[str]
    ) -> tuple[list[Document], list[int]]:
        """按 KB 代码过滤文档，返回 (子集文档, 原始索引列表)。"""
        subset: list[Document] = []
        indices: list[int] = []
        for idx, doc in enumerate(docs):
            kb_code = (doc.metadata or {}).get("kb_code", "")
            if kb_code in kb_codes:
                subset.append(doc)
                indices.append(idx)
        return subset, indices

    async def search_kb(
        self,
        query: str,
        kb_codes: list[str],
        user_id: str = "default",
        top_k: int = 4,
    ) -> list[Document]:
        """在指定 KB 子库中混合检索：关键词 + 向量 → RRF → top-k。"""
        if not query or not kb_codes:
            return []

        all_docs = self.get_store(user_id)
        subset_docs, orig_indices = self._filter_by_kb_codes(all_docs, kb_codes)
        if not subset_docs:
            return []

        orig_set: set[int] = set(orig_indices)

        # 关键词搜索在子集内
        kw = self._keyword_search(query, subset_docs)
        kw_mapped = [(score, orig_indices[i]) for score, i in kw if i < len(orig_indices)]

        # 向量搜索在全集中，但只保留子集内的结果
        emb = await self.ensure_embeddings(user_id)
        vec = await self._vector_search(query, emb)
        vec_filtered = [(score, idx) for score, idx in vec if idx in orig_set]

        merged = self._rrf_fusion(kw_mapped, vec_filtered)
        return [all_docs[i] for i in merged[:top_k] if i < len(all_docs)]

    # ================================================================
    # 图节点 — 三路并行检索 → 聚合
    # ================================================================
    async def _retrieve_remote(
        self,
        biz_query: str | None,
        test_query: str | None,
        stock_query: str | None,
    ) -> tuple[list[Document], list[Document], list[Document], list[Document]]:
        """通过下游 KB REST API 做分库检索。

        2026-08-07 修复：并发 4 路各自新建 httpx.AsyncClient 时，KB 单 worker
        偶发拒绝连接（随机某路 502/失败）。改为共享单个 AsyncClient + 信号量
        限制并发为 2 + 失败重试 2 次。
        """
        import asyncio
        import httpx

        base_url = os.environ.get("KB_BASE_URL", "").rstrip("/")
        timeout = float(os.environ.get("KB_TIMEOUT_SECONDS", "30"))
        # 并发限制：KB 单 worker 并发处理能力有限，2 路并发更稳
        _semaphore = asyncio.Semaphore(2)

        async def _remote_search(query: str | None, kb_codes: list[str]) -> list[Document]:
            if not query:
                return []
            async with _semaphore:
                last_exc: Exception | None = None
                for attempt in range(3):  # 最多 3 次尝试（1 次 + 2 次重试）
                    try:
                        async with httpx.AsyncClient(base_url=base_url, timeout=timeout, trust_env=False) as client:
                            response = await client.post(
                                "/api/v1/search",
                                json={"query": query, "kb_codes": kb_codes, "top_k": 4},
                            )
                            response.raise_for_status()
                            results = response.json().get("results") or []
                        return [
                            Document(
                                page_content=r.get("content", ""),
                                metadata=r.get("metadata", {}),
                            )
                            for r in results
                        ]
                    except Exception as exc:
                        last_exc = exc
                        if attempt < 2:
                            await asyncio.sleep(0.3 * (attempt + 1))  # 退避重试
                # 全部重试失败
                if os.environ.get("ALLOW_LOCAL_KB_FALLBACK", "false").lower() == "true":
                    print(f"  [KB远程检索失败，显式降级为空结果] {kb_codes}: {last_exc}")
                    return []
                raise RuntimeError(
                    f"knowledge_base_unavailable: {kb_codes} 检索失败"
                ) from last_exc

        return await asyncio.gather(
            _remote_search(biz_query, ["KB01", "KB03"]),
            _remote_search(test_query, ["KB05", "KB04"]),
            _remote_search(test_query, ["KB06"]),
            _remote_search(stock_query, ["KB02"]),
        )

    @staticmethod
    def _aggregate_results(
        biz_result: list[Document],
        test_practice_result: list[Document],
        test_standard_result: list[Document],
        regulatory_result: list[Document],
    ) -> str:
        """将四个库的检索结果拼接为聚合文本。"""
        parts: list[str] = []
        for label, docs in [
            ("业务库", biz_result),
            ("创业板法规", regulatory_result),
            ("测试实操库", test_practice_result),
            ("测试制度库", test_standard_result),
        ]:
            if docs:
                parts.append(f"## {label}\n" + "\n\n".join(
                    f"[{d.metadata.get('source', '?')}]\n{d.page_content}" for d in docs
                ))
        return "\n\n---\n\n".join(parts)

    async def retrieve_all(
        self, state: AgentState, *, config: RunnableConfig
    ) -> dict:
        """检索节点：biz / test / stock 三路并行 → 聚合。

        根据 KB_BASE_URL 环境变量切换数据源:
            - 未配置       本地的 knowledge_base/
            - 配置了 URL    下游 KB REST API
        """
        import asyncio

        user_id = config.get("configurable", {}).get("user_id", "default")
        kb_base_url = os.environ.get("KB_BASE_URL", "")
        biz_query = state.get("biz_query")
        test_query = state.get("test_query")
        stock_query = state.get("stock_query")

        if kb_base_url:
            biz_result, test_practice_result, test_standard_result, regulatory_result = \
                await self._retrieve_remote(biz_query, test_query, stock_query)
        elif os.environ.get("ALLOW_LOCAL_KB_FALLBACK", "false").lower() == "true":
            biz_result, test_practice_result, test_standard_result, regulatory_result = \
                await asyncio.gather(
                    self.search_kb(biz_query or "", ["KB01", "KB03"], user_id),
                    self.search_kb(test_query or "", ["KB05", "KB04"], user_id),
                    self.search_kb(test_query or "", ["KB06"], user_id),
                    self.search_kb(stock_query or "", ["KB02"], user_id),
                )
        else:
            raise RuntimeError(
                "knowledge_base_unavailable: 未配置 KB_BASE_URL，且本地知识库降级未启用"
            )

        aggregated = self._aggregate_results(
            biz_result, test_practice_result,
            test_standard_result, regulatory_result,
        )

        return {
            "biz_result": biz_result,
            "test_practice_result": test_practice_result,
            "test_standard_result": test_standard_result,
            "regulatory_result": regulatory_result,
            "aggregated_context": aggregated,
        }


# 模块级默认实例
default_retriever = HybridRetriever()
