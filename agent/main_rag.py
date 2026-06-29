"""PlateAgent Day 5 — ChromaDB RAG 知识库验证

验证目标：
    1. 黑名单精确匹配 + 模糊匹配
    2. 混淆字符检索（SVM 低置信度辅助决策）
    3. 车牌规范文档 RAG 查询
    4. 端到端：format_output_node 接入真实黑名单

用法:
    cd plate-agent
    python -m agent.main_rag
"""

import sys
import os

# 确保项目根目录在 path 中
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent.knowledge.loader import get_knowledge_base, reset_knowledge_base
from agent.tools.knowledge import tool_search_blacklist, tool_lookup_confusion


def test_blacklist_search():
    """场景1：黑名单检索"""
    print("\n" + "=" * 60)
    print("场景1: 黑名单检索 — 精确匹配 + 模糊匹配")
    print("=" * 60)

    # 精确匹配
    result = tool_search_blacklist("京A12345")
    print(f"\n精确查询 京A12345:")
    print(f"  hit={result['hit']}, records={len(result['records'])}")
    for r in result["records"]:
        print(f"    [{r['type']}] {r['plate_number']} — {r['description'][:40]}...")

    # 不存在的车牌
    result = tool_search_blacklist("京Z99999")
    print(f"\n查询未命中车牌 京Z99999:")
    print(f"  hit={result['hit']}, message={result.get('message', '')}")

    # 模糊匹配：查询黑名单中存在的车牌
    result = tool_search_blacklist("粤B88888")
    print(f"\n查询肇事逃逸车辆 粤B88888:")
    print(f"  hit={result['hit']}, records={len(result['records'])}")
    for r in result["records"]:
        print(f"    [{r['type']}] {r['plate_number']} — {r['description'][:40]}...")


def test_confusion_lookup():
    """场景2：混淆字符检索"""
    print("\n" + "=" * 60)
    print("场景2: 混淆字符检索 — SVM 低置信度辅助")
    print("=" * 60)

    for test_char in ["0", "京", "B", "2"]:
        result = tool_lookup_confusion(test_char)
        print(f"\n字符 '{test_char}' 的易混淆候选:")
        if result["status"] == "ok":
            for c in result["candidates"]:
                print(f"    → {c['char']}（{c['category']}）")
        else:
            print(f"    查询失败: {result.get('message', '')}")


def test_plate_specs_rag():
    """场景3：车牌规范文档 RAG 查询"""
    print("\n" + "=" * 60)
    print("场景3: 车牌规范文档 RAG 查询")
    print("=" * 60)

    kb = get_knowledge_base()

    queries = [
        "新能源车牌颜色",
        "蓝牌和黄牌区别",
        "省份简称对照",
    ]
    for q in queries:
        results = kb.search_plate_specs(q, n_results=1)
        print(f"\n查询: {q}")
        if results:
            r = results[0]
            title = r["section_title"]
            dist = r["distance"]
            preview = r["content"][:80].replace("\n", " ")
            print(f"  命中: [{title}] (dist={dist}) — {preview}...")
        else:
            print(f"  未找到相关段落")


def test_stats():
    """场景4：知识库统计"""
    print("\n" + "=" * 60)
    print("场景4: 知识库统计")
    print("=" * 60)

    kb = get_knowledge_base()
    stats = kb.get_stats()
    print(f"\n持久化目录: {stats['persist_dir']}")
    for name, count in stats["collections"].items():
        print(f"  {name}: {count} 条")


def main():
    print("PlateAgent Day 5 — ChromaDB RAG 知识库验证")
    print("Embedding: SimpleChineseEmbedding (char n-gram + hashing trick)")

    # 重置知识库（确保使用最新数据）
    reset_knowledge_base()

    test_stats()
    test_blacklist_search()
    test_confusion_lookup()
    test_plate_specs_rag()

    print("\n" + "=" * 60)
    print("Day 5 RAG 验证完成!")
    print("=" * 60)


if __name__ == "__main__":
    main()
