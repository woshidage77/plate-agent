"""PlateAgent ChromaDB 知识库加载器 — Day 5

三个知识集合：
    blacklist      — 车辆违章黑名单（向量检索）
    plate_specs    — 车牌号牌规范文档（RAG 查询）
    confusion_chars — SVM 易混淆字符对照表

Embedding 策略：
    使用 sklearn TfidfVectorizer 做字符级 n-gram 向量化。
    无需下载模型，纯本地计算，适合 demo 和离线环境。
    生产环境可替换为 sentence-transformers 等更强模型。
"""

import json
import os
import logging
from typing import Optional

import chromadb
from chromadb.config import Settings
from chromadb.api.types import EmbeddingFunction, Documents, Embeddings
import numpy as np

logger = logging.getLogger(__name__)

# ── 默认配置 ──
_DEFAULT_PERSIST_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "chroma_data"
)
_DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")

COLLECTION_BLACKLIST = "plate_blacklist"
COLLECTION_PLATE_SPECS = "plate_specs"
COLLECTION_CONFUSION = "confusion_chars"

# ── 自定义 Embedding Function ──

class SimpleChineseEmbedding(EmbeddingFunction):
    """基于字符 n-gram 计数向量的轻量级中文文本向量化。

    特点：
        - 无需下载模型，纯本地计算
        - 字符级 1-gram 和 2-gram 混合特征
        - 计数向量 + L2 归一化（等价于余弦相似度检索）
        - 全局词典：所有出现过的 n-gram 统一索引，零碰撞

    适用场景：demo、原型验证、离线环境。
    生产建议：替换为 sentence-transformers 或 text2vec 等模型。
    """

    def __init__(self, dim: int = 512):
        """dim 仅用于兼容接口，实际维度由全局词典大小决定。"""
        self._vocab = {}  # n-gram → index（全局共享）
        self._vocab_size = 0

    def _extract_ngrams(self, text: str) -> list[str]:
        """从文本提取字符级 1-gram 和 2-gram。"""
        text = text.lower().strip()
        ngrams = []
        for ch in text:
            if ch.strip():
                ngrams.append("1:" + ch)  # 1-gram 前缀区分
        for i in range(len(text) - 1):
            bigram = text[i:i+2]
            if bigram.strip():
                ngrams.append("2:" + bigram)  # 2-gram 前缀区分
        return ngrams

    def _build_vocab(self, all_docs: list[str]) -> None:
        """从全部文档构建全局词典（一次性）。"""
        for doc in all_docs:
            for ng in self._extract_ngrams(doc):
                if ng not in self._vocab:
                    self._vocab[ng] = len(self._vocab)
        self._vocab_size = len(self._vocab)

    def _doc_to_vec(self, ngrams: list[str]) -> list[float]:
        """将 n-gram 列表转为计数向量。"""
        vec = [0.0] * self._vocab_size
        for ng in ngrams:
            idx = self._vocab.get(ng)
            if idx is not None:
                vec[idx] += 1.0
        # L2 归一化
        norm = np.sqrt(sum(v * v for v in vec))
        if norm > 0:
            vec = [v / norm for v in vec]
        return vec

    def __call__(self, input: Documents) -> Embeddings:
        """将文档列表转为向量列表。

        首次调用时自动从全部文档构建词典。
        """
        # 首次调用：构建全局词典
        if self._vocab_size == 0:
            self._build_vocab(list(input))

        embeddings = []
        for doc in input:
            ngrams = self._extract_ngrams(doc)
            vec = self._doc_to_vec(ngrams)
            embeddings.append(vec)
        return embeddings


# ── KnowledgeBase ──

class KnowledgeBase:

    def __init__(self, persist_dir: Optional[str] = None):
        self._persist_dir = persist_dir or _DEFAULT_PERSIST_DIR
        os.makedirs(self._persist_dir, exist_ok=True)

        self._embed_fn = SimpleChineseEmbedding(dim=512)

        self._client = chromadb.PersistentClient(
            path=self._persist_dir,
            settings=Settings(anonymized_telemetry=False),
        )
        self._initialized = False

    def initialize(self) -> None:
        if self._initialized:
            return

        logger.info("ChromaDB 知识库初始化中... persist_dir=%s", self._persist_dir)

        self._blacklist = self._client.get_or_create_collection(
            name=COLLECTION_BLACKLIST,
            metadata={"description": "车辆违章黑名单"},
            embedding_function=self._embed_fn,
        )
        self._plate_specs = self._client.get_or_create_collection(
            name=COLLECTION_PLATE_SPECS,
            metadata={"description": "车牌号牌规范文档"},
            embedding_function=self._embed_fn,
        )
        self._confusion = self._client.get_or_create_collection(
            name=COLLECTION_CONFUSION,
            metadata={"description": "SVM 易混淆字符对照表"},
            embedding_function=self._embed_fn,
        )

        if self._blacklist.count() == 0:
            self._ingest_blacklist()
        if self._plate_specs.count() == 0:
            self._ingest_plate_specs()
        if self._confusion.count() == 0:
            self._ingest_confusion_chars()

        self._initialized = True
        logger.info(
            "ChromaDB 初始化完成: blacklist=%d, specs=%d, confusion=%d",
            self._blacklist.count(),
            self._plate_specs.count(),
            self._confusion.count(),
        )

    # ── 数据导入 ──

    def _ingest_blacklist(self) -> None:
        path = os.path.join(_DATA_DIR, "blacklist.json")
        if not os.path.exists(path):
            logger.warning("黑名单数据文件不存在: %s", path)
            return

        with open(path, "r", encoding="utf-8") as f:
            records = json.load(f)

        ids, docs, metadatas = [], [], []
        for i, r in enumerate(records):
            ids.append(f"bl_{i}")
            docs.append(
                "车牌号：" + r["plate_number"] + "。"
                "类型：" + r["type"] + "。"
                "描述：" + r["description"] + "。"
                "来源：" + r["source"] + "。"
            )
            metadatas.append({
                "plate_number": r["plate_number"],
                "type": r["type"],
                "date": r["date"],
                "status": r["status"],
                "source": r["source"],
            })

        self._blacklist.add(ids=ids, documents=docs, metadatas=metadatas)
        logger.info("黑名单数据导入完成: %d 条", len(records))

    def _ingest_plate_specs(self) -> None:
        path = os.path.join(_DATA_DIR, "plate_specs.txt")
        if not os.path.exists(path):
            logger.warning("车牌规范文档不存在: %s", path)
            return

        with open(path, "r", encoding="utf-8") as f:
            text = f.read()

        sections = []
        current_title = ""
        current_lines = []

        for line in text.splitlines():
            # 按 ## 和 # 标题分段（跳过文档主标题）
            if line.startswith("## ") or (line.startswith("# ") and not line.startswith("# 中华")):
                if current_title and current_lines:
                    sections.append((current_title, "\n".join(current_lines).strip()))
                current_title = line.lstrip("# ").strip()
                current_lines = []
            elif current_title:  # 只在有标题后才收集内容（跳过头部的目录）
                current_lines.append(line)
        if current_title and current_lines:
            sections.append((current_title, "\n".join(current_lines).strip()))

        ids, docs, metadatas = [], [], []
        for i, (title, content) in enumerate(sections):
            if not content.strip():
                continue
            ids.append(f"spec_{i}")
            docs.append("## " + title + "\n" + content)
            metadatas.append({"section_title": title})

        self._plate_specs.add(ids=ids, documents=docs, metadatas=metadatas)
        logger.info("车牌规范文档导入完成: %d 个段落", len(ids))

    def _ingest_confusion_chars(self) -> None:
        path = os.path.join(_DATA_DIR, "confusion_chars.json")
        if not os.path.exists(path):
            logger.warning("混淆字符数据文件不存在: %s", path)
            return

        with open(path, "r", encoding="utf-8") as f:
            pairs = json.load(f)

        ids, docs, metadatas = [], [], []
        for i, p in enumerate(pairs):
            ids.append(f"cf_{i}")
            docs.append(
                "字符 " + p["char1"] + " 和字符 " + p["char2"] + " 容易混淆。"
                "类别：" + p["category"] + "。"
                "原因：" + p["reason"]
            )
            metadatas.append({
                "char1": p["char1"],
                "char2": p["char2"],
                "category": p["category"],
            })

        self._confusion.add(ids=ids, documents=docs, metadatas=metadatas)
        logger.info("混淆字符导入完成: %d 对", len(pairs))

    # ── 查询接口 ──

    def search_blacklist(self, plate_number: str, n_results: int = 5) -> list[dict]:
        """混合检索：向量召回 + 字符串精确过滤。

        步骤：
            1. 向量检索粗筛（字符 n-gram 相似度）
            2. 提取查询车牌的数字部分（后5位）
            3. 精确过滤：只保留数字部分匹配的记录
            4. 完全匹配的记录排在最前面

        这体现了生产 RAG 的核心模式：
        Embedding 负责"语义相似"的召回，确定性规则负责"精确匹配"的排序。
        """
        self.initialize()

        # 提取数字部分用于精确过滤
        # 车牌格式: 京A12345 → digits="12345"
        query_digits = "".join(
            ch for ch in plate_number if ch.isdigit() or ch.isalpha()
        )[-5:] if len(plate_number) >= 3 else plate_number

        try:
            results = self._blacklist.query(
                query_texts=["车牌号 " + plate_number + " 违章 黑名单"],
                n_results=min(self._blacklist.count(), 15),
            )
        except Exception as e:
            logger.error("黑名单搜索失败: %s", e)
            return []

        records = []
        exact_hit = False

        if results["ids"] and results["ids"][0]:
            for i in range(len(results["ids"][0])):
                meta = results["metadatas"][0][i] if results["metadatas"] else {}
                distance = (
                    results["distances"][0][i]
                    if results["distances"] and results["distances"][0]
                    else float("inf")
                )
                result_plate = meta.get("plate_number", "")
                result_digits = "".join(
                    ch for ch in result_plate if ch.isdigit() or ch.isalpha()
                )[-5:]

                # 精确过滤：数字部分必须匹配
                if query_digits != result_digits:
                    continue

                # 完全匹配标记
                if result_plate == plate_number:
                    exact_hit = True
                    distance = 0.0  # 完全匹配 → 距离归零
                elif plate_number[-5:] in result_plate:
                    distance = distance * 0.5

                records.append({
                    "plate_number": result_plate,
                    "type": meta.get("type", ""),
                    "date": meta.get("date", ""),
                    "description": meta.get("description", ""),
                    "status": meta.get("status", ""),
                    "source": meta.get("source", ""),
                    "distance": round(distance, 4),
                })

        if exact_hit and len(records) > 1:
            # 完全匹配排第一，其余按向量距离
            records.sort(key=lambda r: (0 if r["distance"] == 0.0 else 1, r["distance"]))

        return records[:n_results]

    def search_confusion_chars(self, char: str, n_results: int = 5) -> list[dict]:
        self.initialize()
        # 召回阶段：取所有候选（数据量小，全量检索）
        try:
            results = self._confusion.query(
                query_texts=["字符 " + char + " 和字符 容易混淆 " + char],
                n_results=max(n_results * 2, 20),
            )
        except Exception as e:
            logger.error("混淆字符搜索失败: %s", e)
            return []

        pairs = []
        if results["ids"] and results["ids"][0]:
            for i in range(len(results["ids"][0])):
                meta = results["metadatas"][0][i] if results["metadatas"] else {}
                distance = (
                    results["distances"][0][i]
                    if results["distances"] and results["distances"][0]
                    else float("inf")
                )
                c1 = meta.get("char1", "")
                c2 = meta.get("char2", "")

                # 精确过滤：只保留查询字符出现在 char1 或 char2 中的记录
                if char not in (c1, c2):
                    continue
                # 精确匹配加分
                if c1 == char or c2 == char:
                    distance = distance * 0.5

                pairs.append({
                    "char1": c1,
                    "char2": c2,
                    "category": meta.get("category", ""),
                    "distance": round(distance, 4),
                })

        pairs.sort(key=lambda p: p["distance"])
        return pairs[:n_results]

    def search_plate_specs(self, query: str, n_results: int = 3) -> list[dict]:
        self.initialize()
        try:
            results = self._plate_specs.query(
                query_texts=[query],
                n_results=n_results,
            )
        except Exception as e:
            logger.error("车牌规范搜索失败: %s", e)
            return []

        sections = []
        if results["ids"] and results["ids"][0]:
            for i in range(len(results["ids"][0])):
                meta = results["metadatas"][0][i] if results["metadatas"] else {}
                doc = results["documents"][0][i] if results["documents"] else ""
                distance = (
                    results["distances"][0][i]
                    if results["distances"] and results["distances"][0]
                    else float("inf")
                )
                sections.append({
                    "section_title": meta.get("section_title", ""),
                    "content": doc,
                    "distance": round(distance, 4),
                })
        return sections

    def get_stats(self) -> dict:
        self.initialize()
        return {
            "persist_dir": self._persist_dir,
            "collections": {
                COLLECTION_BLACKLIST: self._blacklist.count(),
                COLLECTION_PLATE_SPECS: self._plate_specs.count(),
                COLLECTION_CONFUSION: self._confusion.count(),
            },
        }

    def reset(self) -> None:
        try:
            self._client.delete_collection(COLLECTION_BLACKLIST)
            self._client.delete_collection(COLLECTION_PLATE_SPECS)
            self._client.delete_collection(COLLECTION_CONFUSION)
        except Exception:
            pass
        self._initialized = False
        self.initialize()


# ── 模块级单例 ──

_kb_instance: Optional[KnowledgeBase] = None


def get_knowledge_base(persist_dir: Optional[str] = None) -> KnowledgeBase:
    global _kb_instance
    if _kb_instance is None:
        _kb_instance = KnowledgeBase(persist_dir=persist_dir)
        _kb_instance.initialize()
    return _kb_instance


def reset_knowledge_base() -> None:
    global _kb_instance
    if _kb_instance is not None:
        _kb_instance.reset()
    _kb_instance = None





