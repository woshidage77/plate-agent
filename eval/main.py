"""PlateAgent 评测入口

用法:
    cd plate-agent
    python -m eval.main              # 全量评测（30张）
    python -m eval.main --limit 10   # 快速评测（前10张）
    python -m eval.main --output report.md  # 输出 Markdown 报告
"""

import argparse
import asyncio
import os
import sys

from dotenv import load_dotenv
load_dotenv()

# 确保项目根目录在 path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent.session_manager import create_session_service, create_memory_service
from eval.evaluator import PlateEvaluator
from eval.report import generate_text_report, generate_markdown_report


async def main():
    parser = argparse.ArgumentParser(description="PlateAgent 评测")
    parser.add_argument("--limit", type=int, default=None, help="限制评测数量")
    parser.add_argument("--output", type=str, default=None, help="输出 Markdown 报告路径")
    parser.add_argument("--judge", action="store_true", help="启用 LLM Judge 评分（需 DeepSeek API）")
    parser.add_argument("--quiet", action="store_true", help="静默模式")
    args = parser.parse_args()

    # 初始化服务
    session_service = create_session_service(use_redis=False)
    memory_service = create_memory_service(use_redis=False)

    # 构建评测器
    base_dir = os.path.dirname(os.path.abspath(__file__))
    gt_path = os.path.join(base_dir, "dataset", "ground_truth.json")

    evaluator = PlateEvaluator(
        gt_path=gt_path,
        session_service=session_service,
        memory_service=memory_service,
    )

    # 初始化 Judge（可选）
    judge = None
    if args.judge:
        from agent.config import get_model_config
        from eval.judge import LLMJudge
        api_key, base_url, model = get_model_config()
        judge = LLMJudge(api_key=api_key, base_url=base_url, model=model)
        print(f"\nPlateAgent 评测开始（LLM Judge 已启用）")
    else:
        print(f"\nPlateAgent 评测开始")
    print(f"  标注文件: {gt_path}")
    print(f"  样本数:   {len(evaluator.ground_truth)}")
    if args.limit:
        print(f"  限制:     前 {args.limit} 张")
    print()

    # 跑评测
    report = await evaluator.run(limit=args.limit, verbose=not args.quiet, judge=judge)

    # 输出报告
    text_report = generate_text_report(report)
    print(text_report)

    # 可选：输出 Markdown
    if args.output:
        md_report = generate_markdown_report(report)
        out_path = os.path.join(base_dir, args.output)
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(md_report)
        print(f"\nMarkdown 报告已保存: {out_path}")


if __name__ == "__main__":
    asyncio.run(main())

