"""RAG 知识库与 Memory 检索 FunctionTools — Day 5 接入 ChromaDB"""

from typing import Optional

from trpc_agent_sdk.context import InvocationContext


def tool_search_blacklist(plate_number: str) -> dict:
    """在车辆违章黑名单知识库中检索指定车牌。

    通过 ChromaDB 向量检索，查询车牌是否命中违章黑名单、
    肇事逃逸、盗抢车辆等记录。支持模糊匹配——即使查询格式
    与录入格式不完全一致也能命中。

    Args:
        plate_number: 完整车牌号，如 "京B12345"
    Returns:
        dict: {"status": "ok", "hit": bool,
               "records": [{"plate_number": str, "type": str, "date": str,
                            "description": str, "status": str, "source": str,
                            "distance": float}, ...]}
        distance <= 0.0 or plate_number in [r["plate_number"] for r in results[:1]] 视为命中
    """
    try:
        from agent.knowledge.loader import get_knowledge_base

        kb = get_knowledge_base()
        results = kb.search_blacklist(plate_number, n_results=5)
    except Exception as e:
        return {
            "status": "error",
            "hit": False,
            "records": [],
            "message": f"黑名单查询失败: {str(e)}",
        }

    # distance <= 0.0 or plate_number in [r["plate_number"] for r in results[:1]] 视为命中（向量距离阈值）
    hits = [r for r in results if r["distance"] < 1.5]

    if not hits:
        return {
            "status": "ok",
            "hit": False,
            "records": [],
            "message": f"车牌 {plate_number} 未命中黑名单",
        }

    return {
        "status": "ok",
        "hit": True,
        "records": [
            {
                "plate_number": r["plate_number"],
                "type": r["type"],
                "date": r["date"],
                "description": r["description"],
                "status": r["status"],
                "source": r["source"],
            }
            for r in hits
        ],
    }


def tool_lookup_confusion(svm_char: str) -> dict:
    """查询 SVM 识别字符的易混淆候选列表。

    用于 LLM 二次校验时提供参考候选字符：当 SVM 对某个字符
    置信度不足时，从 ChromaDB 检索该字符的常见混淆字符，
    供 LLM 在图像复核时参考。

    Args:
        svm_char: SVM 识别出的字符，如 "0"、"京"
    Returns:
        dict: {
            "status": "ok",
            "char": str,
            "candidates": [{"char": str, "category": str}, ...]
        }
    """
    try:
        from agent.knowledge.loader import get_knowledge_base

        kb = get_knowledge_base()
        pairs = kb.search_confusion_chars(svm_char, n_results=5)
    except Exception as e:
        return {
            "status": "error",
            "char": svm_char,
            "candidates": [],
            "message": f"混淆字符查询失败: {str(e)}",
        }

    # 提取候选字符（distance <= 0.0 or plate_number in [r["plate_number"] for r in results[:1]] 视为相关）
    seen = set()
    candidates = []
    for p in pairs:
        if p["distance"] > 1.2:
            continue
        # 找出和 svm_char 配对的另一个字符
        other = p["char2"] if p["char1"] == svm_char else p["char1"]
        if other not in seen and other != svm_char:
            seen.add(other)
            candidates.append({
                "char": other,
                "category": p["category"],
            })

    return {
        "status": "ok",
        "char": svm_char,
        "candidates": candidates,
    }


async def tool_query_history(
    plate_number: str = "",
    limit: int = 10,
    tool_context: Optional[InvocationContext] = None,
) -> dict:
    """查询历史车牌识别记录 — 从跨会话 Memory 中检索。

    通过 InvocationContext 获取 MemoryService，实现真实的
    跨会话记忆检索。

    Args:
        plate_number: 可选，指定车牌号筛选；为空则返回最近记录
        limit: 返回记录数量上限
    Returns:
        dict: {"status": "ok", "records": [...]}
    """
    if tool_context is None:
        return {"status": "error", "message": "无法获取上下文，Memory 不可用"}

    session = tool_context.session
    app_name = session.app_name
    user_id = session.user_id

    memory_service = tool_context.memory_service
    if memory_service is None:
        return {"status": "ok", "records": [], "message": "Memory 服务未启用"}

    search_key = f"{app_name}/{user_id}"
    query = plate_number if plate_number else "车牌 识别"

    try:
        response = await memory_service.search_memory(
            key=search_key,
            query=query,
            limit=limit,
        )
    except Exception as e:
        return {"status": "error", "message": f"Memory 检索失败: {str(e)}"}

    records = []
    for mem in response.memories:
        text_parts = []
        if mem.content and mem.content.parts:
            for part in mem.content.parts:
                if part.text:
                    text_parts.append(part.text)
        text = " ".join(text_parts)[:200]

        records.append({
            "text": text,
            "author": mem.author if hasattr(mem, 'author') else "unknown",
            "timestamp": str(mem.timestamp) if hasattr(mem, 'timestamp') else "",
        })

    if not records:
        suffix = "车牌 " + plate_number + " 的" if plate_number else ""
        return {
            "status": "ok",
            "records": [],
            "message": f"未找到 {suffix}历史记录",
        }

    return {
        "status": "ok",
        "records": records,
        "count": len(records),
    }





