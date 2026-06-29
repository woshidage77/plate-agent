# PlateAgent Day 5 保姆级详解：ChromaDB RAG 从零理解

> 用类比理解概念，用项目真实代码验证，用完整链路串联一切。

---

## 零、先回答最可能问的：RAG 到底解决了什么问题

### 类比：开卷考试 vs 闭卷考试

- **闭卷考试**：你只能靠记忆回答 → **纯 LLM**
  问："PlateAgent 的黑名单有哪些？" → LLM 瞎编（幻觉）

- **开卷考试**：你可以翻书查资料再回答 → **RAG**
  问："PlateAgent 的黑名单有哪些？" → 先查 ChromaDB → 查到 12 条 → 告诉用户

RAG 的本质就是**给 LLM 配一个资料库**。回答问题前先翻资料，翻到了就基于资料回答，翻不到就说不知道。

### 在你的项目里

当用户识别车牌"京A12345"后，format_output_node 调用 tool_search_blacklist("京A12345")：

```tool_search_blacklist("京A12345")
  ↓
ChromaDB 向量检索 → 找到一条记录：
  "车牌号：京A12345。类型：违章未处理。超速50%以上，记12分"
  ↓
返回给用户：
  "识别结果：京A12345
   ⚠ 黑名单命中：[违章未处理] 京A12345 — 超速50%以上，记12分，罚款2000元"
```

这就是 RAG 的完整闭环。

---

## 一、向量数据库——ChromaDB 是什么

### 1.1 类比：图书馆卡片目录 vs 搜索引擎

| | 传统数据库 (MySQL) | 向量数据库 (ChromaDB) |
|---|---|---|
| 存什么 | 表格（行列） | 向量（浮点数数组） |
| 怎么查 | WHERE plate = '京A12345' | 找"意思最接近"的 |
| 查不到 | 返回空 | 返回"最像的" |

**向量数据库不做精确匹配，做语义相似**。

### 1.2 向量怎么来的

```文本 "京A12345 违章 超速"
  ↓ Embedding Function（把文字变成数字数组）
向量 [0.12, -0.34, 0.87, -0.21, ..., 0.05]  （512个数字）
```

两条意思相近的文本，它们的 512 个数字也"长得像"——这就是向量相似度检索的数学基础。

### 1.3 PlateAgent 用的 Embedding

我们没用 HuggingFace 的大模型（国内下载困难），而是写了一个轻量的 SimpleChineseEmbedding：

- 把文字拆成字（1-gram）和相邻字对（2-gram）
- 给每个字/字对分配一个全局编号（词典）
- 统计每个字/字对出现了几次 → 计数向量
- L2 归一化 → 可以在 ChromaDB 里做余弦相似度搜索

代码在 loader.py：

```python
class SimpleChineseEmbedding(EmbeddingFunction):
    def _extract_ngrams(self, text: str) -> list[str]:
        ngrams = []
        for ch in text:         # 1-gram：每个字
            if ch.strip():
                ngrams.append("1:" + ch)
        for i in range(len(text) - 1):  # 2-gram：相邻字对
            bigram = text[i:i+2]
            if bigram.strip():
                ngrams.append("2:" + bigram)
        return ngrams
```

### 1.4 ChromaDB 的三个核心操作

在 loader.py 中，KnowledgeBase 类的核心操作：

```python
# 1. 创建/获取 collection（类似建表）
self._blacklist = self._client.get_or_create_collection(
    name="plate_blacklist",
    embedding_function=self._embed_fn,
)

# 2. 添加数据（类似 INSERT）
self._blacklist.add(
    ids=["bl_0"],
    documents=["车牌号：京A12345。类型：违章未处理。描述：超速50%..."],
    metadatas=[{"plate_number": "京A12345", "type": "违章未处理"}],
)

# 3. 查询（类似 SELECT ... ORDER BY similarity）
results = self._blacklist.query(
    query_texts=["车牌号 京A12345 违章"],
    n_results=5,
)
```

---

## 二、数据怎么导入——幂等设计

### 2.1 什么触发导入

KnowledgeBase.initialize() 在首次调用时检查每个 collection 是否为空：

```python
def initialize(self) -> None:
    if self._initialized:
        return                              # 已初始化，直接返回

    self._blacklist = self._client.get_or_create_collection(...)
    self._plate_specs = self._client.get_or_create_collection(...)
    self._confusion = self._client.get_or_create_collection(...)

    if self._blacklist.count() == 0:        # ← 只在空表时导入
        self._ingest_blacklist()
    if self._plate_specs.count() == 0:
        self._ingest_plate_specs()
    if self._confusion.count() == 0:
        self._ingest_confusion_chars()

    self._initialized = True
```

这意味着：
- 第一次运行 → 自动导入全部数据
- 第二次运行 → 发现 collection 不空 → 跳过导入
- 删掉 chroma_data/ 目录 → 重新导入

这就是**幂等导入**——重复执行不会产生重复数据。

### 2.2 黑名单怎么存的

每一条黑名单记录作为一个 document 存入 ChromaDB。document 内容包含了所有文本字段：

```"车牌号：京A12345。类型：违章未处理。描述：超速50%以上，记12分，罚款2000元。来源：交管系统。"
```

这样向量检索时，查询和 document 的所有文本内容做相似度匹配，不只看车牌号。但结构化字段（plate_number, type, date 等）同时存在 metadata 中，方便后续精确过滤。

---

## 三、混合检索——为什么纯向量不够

### 3.1 问题

黑名单有 12 条记录，查询"京A12345"。所有车牌共享相似结构：

```京A12345 → [京, A, 1, 2, 3, 4, 5, 京A, A1, 12, 23, 34, 45]
沪C54321 → [沪, C, 5, 4, 3, 2, 1, 沪C, C5, 54, 43, 32, 21]
```

两个车牌的 n-gram 几乎完全不相交，但高维空间中 L2 归一化后的向量仍然可能"距离近"——这就是**向量检索对结构化短文本的固有限制**。

### 3.2 解决方案

search_blacklist() 实现了两阶段混合检索：

```python
def search_blacklist(self, plate_number: str, n_results: int = 5):
    # 提取数字部分
    query_digits = "".join(
        ch for ch in plate_number if ch.isdigit() or ch.isalpha()
    )[-5:]  # "京A12345" → "A12345" → "12345"

    # 阶段1: 向量召回
    results = self._blacklist.query(
        query_texts=["车牌号 " + plate_number + " 违章 黑名单"],
        n_results=15,
    )

    # 阶段2: 精确过滤 — 数字部分必须匹配
    for each result:
        result_digits = extract_digits(result.plate_number)[-5:]
        if query_digits != result_digits:
            continue          # ← 数字不匹配的直接丢弃
        # 完全匹配 → distance=0；部分匹配 → 向量距离排序

    return filtered_records
```

这就是生产级 RAG 的常见模式：**向量负责"召回"（不漏），规则负责"精确"（不错）**。

---

## 四、混淆字符 RAG——LLM 复核的弹药库

### 4.1 为什么要做这个

SVM 识别字符时，置信度 < 0.85 就需要 LLM 复核。但 LLM 看一张字符图片做判断也很困难——它不知道这个字符"可能和哪些字符混淆"。

混淆字符 RAG 解决的就是这个问题：**告诉 LLM "这个字符最可能被误认成哪几个"**，让 LLM 在有限候选中做选择题，而不是在全部 6000+ 汉字中做填空题。

### 4.2 完整调用链

在 graph_nodes.py 的 llm_verify_node 中：

```python
# SVM 认为字符是 "0"，但置信度只有 0.6
svm_char = "0"

# 从 ChromaDB 查混淆候选
confusion_result = tool_lookup_confusion(svm_char)
# → candidates: ["Q", "D", "O"]

# 告诉 LLM：
# "SVM 认为这是 0，但它可能和 Q、D、O 混淆。
#  请你在 0/Q/D/O 中选择最像的那个。"
```

tool_lookup_confusion 的实现（knowledge.py）：

```python
def tool_lookup_confusion(svm_char: str) -> dict:
    kb = get_knowledge_base()
    pairs = kb.search_confusion_chars(svm_char, n_results=5)

    # 从混淆对中提取候选字符
    candidates = []
    for p in pairs:
        other = p["char2"] if p["char1"] == svm_char else p["char1"]
        if other not in seen and other != svm_char:
            candidates.append({"char": other, "category": p["category"]})

    return {"status": "ok", "char": svm_char, "candidates": candidates}
```

---

## 五、从零到一的代码流程回顾

```config.py                  ──→ CHROMA_PERSIST_DIR = "./chroma_data"
                               ↓
agent/knowledge/data/      ──→ blacklist.json (12条)
                               plate_specs.txt (5章节)
                               confusion_chars.json (20对)
                               ↓
agent/knowledge/loader.py  ──→ SimpleChineseEmbedding (字符n-gram计数向量)
                               KnowledgeBase (PersistentClient + 3个Collection)
                               get_knowledge_base() (单例)
                               ↓
agent/tools/knowledge.py   ──→ tool_search_blacklist (ChromaDB混合检索)
                               tool_lookup_confusion (混淆字符查询)
                               ↓
agent/graph_nodes.py       ──→ llm_verify_node (查混淆字符 → 帮LLM决策)
                               format_output_node (查黑名单 → 附加到结果)
                               ↓
agent/main_rag.py          ──→ 验证：黑名单/混淆/规范文档 全通
```

---

## 六、考试速记卡

| 考点 | 答案 |
|------|------|
| RAG 三个字母含义？ | Retrieval（检索）+ Augmented（增强）+ Generation（生成） |
| 向量数据库和传统数据库区别？ | 向量数据库做语义相似度搜索，传统数据库做精确匹配 |
| ChromaDB 的两种 Client？ | PersistentClient（本地落盘） / HttpClient（远程服务） |
| Collection 是什么？ | ChromaDB 的"表"，存储 documents + embeddings + metadata |
| Embedding 做什么？ | 把文本转成固定维度浮点数向量 |
| PlateAgent 的 Embedding 方案？ | 字符 n-gram 计数向量（全局词典），零下载 |
| 混合检索的两阶段？ | 向量召回（粗筛15条）→ 精确过滤（数字部分比对） |
| 混淆字符 RAG 的用途？ | SVM 低置信度时，给 LLM 提供候选字符列表做辅助决策 |
| 幂等导入怎么实现？ | 检查 collection.count() == 0，只在空表时导入 |
| PlateAgent 三个 ChromaDB Collection？ | plate_blacklist / plate_specs / confusion_chars |
