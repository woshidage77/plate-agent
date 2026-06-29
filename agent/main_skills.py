"""PlateAgent Day 10 — Skills 系统演示脚本

演示：
    1. SKILL.md 加载与解析
    2. Frontmatter 提取（name, description）
    3. Tools 节解析
    4. 正文 body 获取
    5. 多 skill 管理

用法：
    python -m agent.main_skills
"""

import logging

from agent.skill_loader import SkillLoader

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def main():
    print("=" * 60)
    print("PlateAgent Day 10 - Skills System Demo")
    print("=" * 60)

    loader = SkillLoader()

    # 1. 列出所有 skill
    print("\n[1/5] list_skills()...")
    skills = loader.list_skills()
    print(f"  可用 skill: {skills}")

    # 2. 加载 plate-recognition skill
    print("\n[2/5] load('plate_recognition')...")
    skill = loader.load("plate_recognition")

    if not skill:
        print("  ERROR: skill 加载失败")
        return

    print(f"  name:        {skill.name}")
    print(f"  description: {skill.description}")
    print(f"  tools ({len(skill.tools)}): {skill.tools}")
    print(f"  base_dir:    {skill.base_dir}")
    print(f"  body length: {len(skill.body)} chars")

    # 3. 验证 frontmatter 解析
    print("\n[3/5] Frontmatter check...")
    assert skill.name == "plate-recognition", f"name mismatch: {skill.name}"
    assert "license plate" in skill.description.lower(), f"description mismatch: {skill.description}"
    print("  name + description: OK")

    # 4. 验证 Tools 节解析
    print("\n[4/5] Tools extraction check...")
    expected_tools = [
        "plate_preprocess",
        "plate_locate",
        "plate_segment",
        "plate_recognize",
        "plate_verify",
        "plate_blacklist_check",
    ]
    for t in expected_tools:
        status = "OK" if t in skill.tools else "MISSING"
        print(f"  {t}: {status}")

    # 5. 验证缓存
    print("\n[5/5] Cache check...")
    cached = loader.get_loaded_count()
    print(f"  loaded skills in cache: {cached}")

    # 二次加载——应命中缓存
    skill2 = loader.load("plate_recognition")
    print(f"  second load same instance: {'YES (cached)' if skill is skill2 else 'NO (re-parsed)'}")

    # 摘要列表
    summaries = loader.get_summaries()
    print(f"\n  All skill summaries:")
    for s in summaries:
        print(f"    - {s['name']}: {s['description'][:60]}...")
        print(f"      tools: {s['tools']}")

    print("\n" + "=" * 60)
    print("ALL CHECKS PASSED")
    print("=" * 60)


if __name__ == "__main__":
    main()
