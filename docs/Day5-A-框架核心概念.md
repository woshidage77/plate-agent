# PlateAgent Day 5-A：ChromaDB RAG 框架知识（考试向）

> 源：ChromaDB 官方文档 + tRPC-Agent Knowledge 模块 + 项目实战
> 用途：7.1 犀牛鸟考试知识储备

---

## 一、RAG 是什么——从类比开始

### 1.1 不用 RAG 的问题

你问 ChatGPT "PlateAgent 项目的黑名单有哪些车牌？"

ChatGPT 不知道——它的训练数据里没有你的项目内容。它要么瞎编（幻觉），要么说不知道。

### 1.2 RAG 的解决思路

RAG = Retrieval-Augmented Generation（检索增强生成）

```用户提问
  ↓
① 检索（Retrieval）：从你的知识库中找到相关文档
  ↓
② 增强（Augmented）：把检索到的文档作为上下文注入 Prompt
  ↓
③ 生成（Generation）：模型基于"问题 + 检索到的文档"生成回答
```

一句话：**给模型配备一个"资料库"，回答问题前先查资料**。

### 1.3 在你的项目里

| RAG 阶段 | PlateAgent 实现 |
|---------|----------------|
| 知识库 | 三个 ChromaDB Collection：黑名单 / 规范文档 / 混淆字符 |
| 检索 | search_blacklist() / search_confusion_chars() / search_plate_specs() |
| 增强 | LLM 复核时提供混淆候选列表；输出结果时附加黑名单信息 |
| 生成 | DeepSeek Chat 基于检索结果生成最终回复 |

---

## 二、向量数据库是什么

### 2.1 传统数据库 vs 向量数据库

| | MySQL | ChromaDB |
|---|-------|----------|
| 存什么 | 结构化数据（行/列） | 向量（浮点数数组） |
| 怎么查 | WHERE plate = '京A12345'（精确匹配） | 找"最相似"的向量（语义匹配） |
| 查不到时的行为 | 返回空 | 返回"最接近的"，即使不完全匹配 |

### 2.2 向量怎么来——Embedding

```文本 "车牌号：京A12345。类型：违章未处理。"
  ↓ Embedding Function
向量 [0.12, -0.34, 0.87, ..., 0.05]  （例如 512 维）
```

两个"意思相近"的文本，它们的向量在空间中"距离近"。

### 2.3 距离度量

ChromaDB 默认使用 **余弦距离**：

- distance=0 → 完全相同
- distance=1 → 正交（无关）
- distance=2 → 完全相反

---

## 三、ChromaDB 核心概念

### 3.1 架构

| 概念 | 类比 | PlateAgent 中的实例 |
|------|------|-------------------|
| Client | 数据库连接 | PersistentClient(path="./chroma_data") |
| Collection | 表 | plate_blacklist, plate_specs, confusion_chars |
| Document | 一行文本 | "车牌号：京A12345。类型：违章未处理..." |
| Embedding | 向量 | [0.12, -0.34, ...] (512维) |
| Metadata | 附加字段 | plate_number / type / status 等结构化字段 |

### 3.2 两种 Client 模式

| 模式 | 代码 | 持久化 | 适用 |
|------|------|--------|------|
| PersistentClient | chromadb.PersistentClient(path="./data") | 落盘 | 本地开发、单机部署 |
| HttpClient | chromadb.HttpClient(host="...", port=8000) | 服务端 | 微服务架构 |

### 3.3 核心操作

```python
# 创建/获取 collection
collection = client.get_or_create_collection(
    name="plate_blacklist",
    embedding_function=my_embed_fn,
)

# 添加数据
collection.add(
    ids=["bl_0"],
    documents=["车牌号：京A12345。类型：违章未处理。"],
    metadatas=[{"plate_number": "京A12345"}],
)

# 查询
results = collection.query(
    query_texts=["车牌号 京A12345 违章"],
    n_results=5,
)
# results["ids"][0]       → ["bl_0", ...]
# results["distances"][0] → [0.32, ...]
# results["metadatas"][0] → [{"plate_number": "京A12345"}, ...]
```

---

## 四、Embedding 策略对比

### 4.1 三种方案

| 方案 | 代表 | 优点 | 缺点 |
|------|------|------|------|
| 云端 API | OpenAI text-embedding-3 | 最强效果 | 需要网络、API费用 |
| 本地模型 | sentence-transformers | 效果好、离线可用 | 需下载模型(~90MB) |
| 轻量算法 | TF-IDF / n-gram计数 | 零下载、极快 | 语义理解弱 |

### 4.2 PlateAgent 的选择

Day 5 使用了**字符 n-gram 计数向量**（SimpleChineseEmbedding）：

- 1-gram（单字符）+ 2-gram（双字符对）
- 全局词典，零碰撞
- L2 归一化，等价于余弦相似度

**为什么不用 sentence-transformers？** 国内网络下载 HuggingFace 模型困难，demo 阶段优先零依赖方案。生产环境替换为更强的 embedding 模型仅需改一行代码（embedding_function 参数）。

---

## 五、混合检索——RAG 的工程实践

### 5.1 纯向量检索的问题

对于黑名单这种"精确匹配"场景，纯向量检索有局限：

- 所有车牌共享相似结构（"汉字+字母+5位数字"）
- 向量相似度高但实际不匹配
- 例如：查询"京A12345"，可能召回"沪C54321"（结构相似，内容无关）

### 5.2 混合检索模式

```阶段1: 向量召回（粗筛）
  查询 → Embedding → ChromaDB.query() → 15个候选

阶段2: 精确过滤（精选）
  候选 → 提取数字部分 → 与查询的数字部分比对 → 只保留匹配的

阶段3: 排序
  精确匹配 → distance=0 → 排最前
  部分匹配 → 按向量距离排序
```

### 5.3 代码证据

loader.py 的 search_blacklist() 方法实现了完整的混合检索模式。

---

## 六、考试速记卡

| 考点 | 答案 |
|------|------|
| RAG 三个字母含义？ | Retrieval（检索）+ Augmented（增强）+ Generation（生成） |
| 向量数据库和传统数据库区别？ | 向量数据库做语义相似度搜索，传统数据库做精确匹配 |
| ChromaDB 的两种 Client？ | PersistentClient（本地） / HttpClient（远程） |
| Collection 是什么？ | 类似于数据库的"表"，存储 documents + embeddings + metadata |
| Embedding 做什么？ | 把文本转成固定维度向量 |
| 余弦距离 0/1/2 含义？ | 0=完全相同，1=正交无关，2=完全相反 |
| 混合检索的价值？ | 向量召回保证"不漏"，精确过滤保证"不错" |
| PlateAgent 用了什么 Embedding？ | 字符 n-gram 计数向量（512维全局词典） |
| Collection 的 add() 参数？ | ids, documents, metadatas |
| Collection 的 query() 返回？ | ids, distances, metadatas, documents（四元组） |
