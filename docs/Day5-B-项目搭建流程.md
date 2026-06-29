# PlateAgent Day 5-B：ChromaDB RAG 搭建流程

> 从零搭建 ChromaDB 向量知识库的完整步骤

---

## 一、文件变更清单

| 操作 | 文件 | 说明 |
|------|------|------|
| 新增 | agent/knowledge/data/blacklist.json | 12条车辆黑名单 |
| 新增 | agent/knowledge/data/plate_specs.txt | 车牌规范文档（5章节） |
| 新增 | agent/knowledge/data/confusion_chars.json | 20对SVM易混淆字符 |
| 新增 | agent/knowledge/loader.py | ChromaDB加载器 + 自定义Embedding |
| 修改 | agent/config.py | 新增 ChromaDB 配置 |
| 修改 | agent/tools/knowledge.py | 新增 tool_lookup_confusion + tool_search_blacklist接入真实ChromaDB |
| 修改 | agent/graph_agent.py | 注册 tool_lookup_confusion |
| 修改 | agent/graph_nodes.py | llm_verify_node 增强（混淆字符RAG） + format_output_node 增强（真实黑名单） |
| 新增 | agent/main_rag.py | RAG验证脚本 |

---

## 二、环境配置

### 2.1 requirements.txt

已包含 chromadb>=0.4.0（项目初始化时已安装）。

### 2.2 .env 配置

```env
CHROMA_PERSIST_DIR=./chroma_data
```

### 2.3 config.py 新增

```python
CHROMA_PERSIST_DIR = os.getenv("CHROMA_PERSIST_DIR", "./chroma_data")
CHROMA_COLLECTION_BLACKLIST = "plate_blacklist"
CHROMA_COLLECTION_PLATE_SPECS = "plate_specs"
CHROMA_COLLECTION_CONFUSION = "confusion_chars"
```

---

## 三、数据准备

### 3.1 黑名单数据

12 条真实场景的黑名单记录，覆盖 6 种违章类型：

- 违章未处理（超速、闯红灯、逆行）
- 肇事逃逸（追尾逃逸、撞毁护栏）
- 盗抢车辆（停车场被盗、GPS定位）
- 套牌车（套用号牌违章）
- 报废车上路
- 违章王（累计42-56条未处理）

### 3.2 规范文档

5 个章节的车牌规范：

1. 号牌颜色分类（蓝/黄/绿/黑/白）
2. 省份简称编码（31个省/自治区/直辖市）
3. 号牌编码规则（格式+序号规则）
4. 特殊号牌规则（警/军/使馆/临时/挂车）
5. 新能源号牌规则（D纯电动/F插电混动）

### 3.3 混淆字符

20 对 SVM 常见混淆字符：

- 省份汉字：京↔琼、浙↔湘、鲁↔晋、粤↔鄂
- 字母数字：B↔8、0↔O、0↔D、0↔Q、2↔Z、5↔S、1↔I、7↔T、C↔G、E↔F、A↔4、6↔G、9↔P、3↔B、D↔P、K↔X

---

## 四、核心实现

### 4.1 自定义 Embedding

SimpleChineseEmbedding 类：

- 字符 1-gram + 2-gram 特征提取
- 全局词典（所有文档的 n-gram 统一索引）
- 计数向量 + L2 归一化
- 零外部依赖，纯 Python + numpy

### 4.2 ChromaDB 加载器

KnowledgeBase 类：

- PersistentClient 持久化存储
- 三个 Collection：blacklist / plate_specs / confusion_chars
- 幂等数据导入（collection 为空时才导入）
- 单例模式（模块级 get_knowledge_base()）

### 4.3 混合检索

黑名单检索采用两阶段策略：

1. **向量召回**：ChromaDB 向量检索，取 15 个候选
2. **精确过滤**：提取车牌数字部分（后5位），精确比对，只保留匹配的候选

### 4.4 工具更新

| 工具 | 变化 |
|------|------|
| tool_search_blacklist | 从占位 → ChromaDB 混合检索 |
| tool_lookup_confusion | 新增：查询 SVM 字符的易混淆候选 |

---

## 五、验证

运行验证脚本：

```bash
cd plate-agent
python -m agent.main_rag
```

预期输出：

```plate_blacklist: 12 条
plate_specs: 5 条
confusion_chars: 20 条

场景1: 黑名单检索
  京A12345 → 1条记录（违章未处理）
  京Z99999 → 1条记录（数字匹配 苏E99999）
  粤B88888 → 1条记录（肇事逃逸）

场景2: 混淆字符
  0 → Q, D, O
  京 → 琼
  B → 8, 3
  2 → Z

场景3: 规范文档
  新能源车牌颜色 → 新能源号牌规则
  省份简称对照 → 号牌颜色分类
```
