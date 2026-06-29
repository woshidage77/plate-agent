"""PlateAgent Skill Loader — Day 10

Parse SKILL.md files to extract skill metadata, body, tool list, and resources.
A lightweight loader for understanding the core Skills concept —
simpler than the full tRPC-Agent Skills system.

SKILL.md format:
    ---
    name: skill-name
    description: One-line description
    ---

    ## Overview
    ...

    ## Tools
    - tool_name_1
    - tool_name_2

    ## Usage Pattern
    ...

Usage:
    from agent.skill_loader import SkillLoader

    loader = SkillLoader()
    skill = loader.load("skills/plate_recognition")
    print(skill.name, skill.description, skill.tools)
"""

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

DEFAULT_SKILLS_DIR = Path(__file__).parent.parent / "skills"


@dataclass
class SkillInfo:
    """Parsed skill information from SKILL.md."""
    name: str = ""
    description: str = ""
    body: str = ""
    tools: list[str] = field(default_factory=list)
    base_dir: str = ""


class SkillLoader:
    """SKILL.md file parser.

    Capabilities:
        - list_skills(): enumerate available skills
        - load(name): load a skill, return SkillInfo
        - get_summaries(): return summaries for all skills (for skill_list tool)
    """

    def __init__(self, skills_dir: Optional[Path] = None):
        self._skills_dir = Path(skills_dir) if skills_dir else DEFAULT_SKILLS_DIR
        self._cache: dict[str, SkillInfo] = {}

    @staticmethod
    def _parse_frontmatter(text: str) -> tuple[dict, str]:
        """Parse YAML-style frontmatter (simplified — no pyyaml dependency).

        Only parses `key: value` lines. No nesting/lists/quotes support.
        Handles UTF-8 BOM if present.

        Returns:
            (frontmatter_dict, body_after_frontmatter)
        """
        meta: dict[str, str] = {}
        body = text

        # Strip UTF-8 BOM if present
        if text.startswith('\ufeff'):
            text = text[1:]

        if not text.startswith('---'):
            return meta, text

        end_idx = text.find('---', 3)
        if end_idx == -1:
            return meta, text

        fm_block = text[3:end_idx].strip()
        body = text[end_idx + 3:].strip()

        for line in fm_block.split('\n'):
            line = line.strip()
            if ':' in line:
                key, _, val = line.partition(':')
                meta[key.strip()] = val.strip()

        return meta, body

    @staticmethod
    def _extract_tools(body: str) -> list[str]:
        """Extract tool names from the ## Tools section.

        Walks lines after ## Tools header, collects `- tool_name` entries,
        stops at the next ## section header.
        """
        tools: list[str] = []
        lines = body.split('\n')
        in_tools = False

        for line in lines:
            if re.match(r'^##\s+Tools', line):
                in_tools = True
                continue
            if in_tools:
                if re.match(r'^##\s+', line):
                    break
                m = re.match(r'[-*]\s+`?(\w+)`?', line.strip())
                if m:
                    tools.append(m.group(1))

        return tools

    def list_skills(self) -> list[str]:
        """List available skill names."""
        if not self._skills_dir.exists():
            return []
        return sorted(
            entry.name
            for entry in self._skills_dir.iterdir()
            if entry.is_dir() and (entry / "SKILL.md").exists()
        )

    def load(self, name: str) -> Optional[SkillInfo]:
        """Load a skill by directory name.

        Args:
            name: skill directory name (e.g. "plate_recognition")

        Returns:
            SkillInfo or None if not found
        """
        if name in self._cache:
            return self._cache[name]

        skill_dir = self._skills_dir / name
        skill_file = skill_dir / "SKILL.md"
        if not skill_file.exists():
            logger.warning("SKILL.md not found: %s", skill_file)
            return None

        text = skill_file.read_text(encoding="utf-8")
        meta, body = self._parse_frontmatter(text)
        tools = self._extract_tools(body)

        info = SkillInfo(
            name=meta.get("name", name),
            description=meta.get("description", ""),
            body=body,
            tools=tools,
            base_dir=str(skill_dir.resolve()),
        )

        self._cache[name] = info
        logger.info("Skill loaded: %s (%d tools)", name, len(tools))
        return info

    def get_summaries(self) -> list[dict]:
        """Return summaries of all available skills."""
        summaries = []
        for name in self.list_skills():
            skill = self.load(name)
            if skill:
                summaries.append({
                    "name": skill.name,
                    "description": skill.description,
                    "tools": skill.tools,
                })
        return summaries

    def get_loaded_count(self) -> int:
        """Number of skills currently cached."""
        return len(self._cache)