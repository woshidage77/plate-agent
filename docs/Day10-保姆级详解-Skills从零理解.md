# PlateAgent Day 10 保姆级详解：Skills 系统从零理解

> 用类比理解 Skills 概念，用项目真实代码验证。

---

## 零、Skills 解决什么问题

假设你有 10 个 Agent，每个都需要车牌识别能力。没有 Skills 时：

- 每个 Agent 都要重复定义 6 个 FunctionTool
- 每个 Agent 的 system prompt 里都要写一大段"怎么用这些工具"
- 工具更新了（比如加了新算法），10 个 Agent 要挨个改

有 Skills 之后：

- 车牌识别能力封装成一个 `plate-recognition` skill
- 任何 Agent 需要时 `skill_load("plate-recognition")` 就行
- 工具定义和使用说明都在一个 SKILL.md 里，改一处全生效

类比：Skills = 手机 App。你需要拍照 → 下载相机 App → 用它的功能。你不需要在自己手机里从零写相机代码。

---

## 二、SKILL.md 的结构——"技能说明书"

### 2.1 整体结构

```markdown
---
name: plate-recognition          ← 技能名字
description: 车牌识别流水线       ← 一句话描述
---

## Overview                       ← 功能概述
这个技能做什么、怎么用...

## Tools                          ← 暴露哪些工具
- plate_preprocess
- plate_locate
- ...

## Usage Pattern                  ← 使用方式
先 load，再调用工具...

## Examples                       ← 示例
具体怎么用...

## Dependencies                   ← 依赖
需要装什么包...
```

### 2.2 三部分拆解

**Frontmatter（YAML 头）**：`---` 包起来的部分。name 和 description 是给 skill_list 工具看的，帮助 Agent 决定要不要加载这个 skill。

**Body（正文）**：frontmatter 之后的所有内容。Agent 加载 skill 时，这段正文会被拼到 system prompt 里——告诉 Agent "你会用这些工具，这么用"。

**Tools 节**：列出该 skill 暴露的工具名。Agent 加载后，这些工具会自动注册——不需要手动一个个加。

---

## 三、SkillLoader 怎么解析 SKILL.md

代码在 [agent/skill_loader.py](/D:/codex_prorject/ai_project/xiniuniaojia/plate-agent/agent/skill_loader.py)。

### 3.1 三步解析

```python
text = skill_file.read_text(encoding="utf-8")

# 第一步：解析 frontmatter（--- 之间的 YAML）
meta, body = _parse_frontmatter(text)
# meta = {"name": "plate-recognition", "description": "..."}
# body = "## Overview\n\nComplete Chinese license plate..."

# 第二步：从 Tools 节提取工具名列表
tools = _extract_tools(body)
# tools = ["plate_preprocess", "plate_locate", ...]

# 第三步：组装 SkillInfo
info = SkillInfo(
    name=meta["name"],
    description=meta["description"],
    body=body,
    tools=tools,
)
```

### 3.2 Frontmatter 解析源码

```python
@staticmethod
def _parse_frontmatter(text: str) -> tuple[dict, str]:
    # 处理 UTF-8 BOM（Windows 的 Set-Content 会加）
    if text.startswith('\ufeff'):
        text = text[1:]

    if not text.startswith('---'):
        return {}, text

    # 找第二个 ---
    end_idx = text.find('---', 3)
    fm_block = text[3:end_idx].strip()
    body = text[end_idx + 3:].strip()

    # 逐行解析 key: value
    meta = {}
    for line in fm_block.split('\n'):
        if ':' in line:
            key, _, val = line.partition(':')
            meta[key.strip()] = val.strip()

    return meta, body
```

关键细节：用 `text.find('---', 3)` 找**第二个** `---`——第一个在开头，第二个才是 frontmatter 的结束标记。

### 3.3 Tools 节解析源码

```python
@staticmethod
def _extract_tools(body: str) -> list[str]:
    tools = []
    in_tools = False

    for line in body.split('\n'):
        if re.match(r'^##\s+Tools', line):
            in_tools = True      # 进入 Tools 节
            continue
        if in_tools:
            if re.match(r'^##\s+', line):
                break            # 遇到下一个 ## 标题，退出
            m = re.match(r'[-*]\s+`?(\w+)`?', line.strip())
            if m:
                tools.append(m.group(1))

    return tools
```

逐行扫描。`## Tools` 开始收集，下一个 `##` 标题停止。每行 `- tool_name` 提取工具名。

---

## 四、验证结果

```bash
python -m agent.main_skills
```

```
============================================================
PlateAgent Day 10 - Skills System Demo
============================================================

[1/5] list_skills()...
  可用 skill: ['plate_recognition']

[2/5] load('plate_recognition')...
  name:        plate-recognition
  description: Chinese license plate recognition pipeline...
  tools (6): ['plate_preprocess', 'plate_locate', 'plate_segment',
              'plate_recognize', 'plate_verify', 'plate_blacklist_check']
  base_dir:    D:\...\skills\plate_recognition
  body length: 2711 chars

[3/5] Frontmatter check...
  name + description: OK

[4/5] Tools extraction check...
  plate_preprocess: OK
  plate_locate: OK
  plate_segment: OK
  plate_recognize: OK
  plate_verify: OK
  plate_blacklist_check: OK

[5/5] Cache check...
  loaded skills in cache: 1
  second load same instance: YES (cached)

============================================================
ALL CHECKS PASSED
============================================================
```

---

## 五、Skills 和 FunctionTool 的关系

| | FunctionTool | Skill |
|---|---|---|
| 粒度 | 单个函数 | 一组工具 + 使用文档 |
| 注册方式 | `FunctionTool(func=xxx)` | `skill_load("name")` |
| 使用文档 | 只有函数 docstring | SKILL.md 正文拼到 system prompt |
| 延迟加载 | 不支持（注册即占用 token） | 支持（load 前不占 token） |
| 复用性 | 低（每个 Agent 手动注册） | 高（一次定义，多处 load） |

**一句话**：Skill 是 FunctionTool 的"打包升级版"——把一组相关工具和它们的使用说明打成一个包，按需加载。

---

## 六、考试常见误区

| 误区 | 正解 |
|------|------|
| "SKILL.md 是代码文件" | 不是。SKILL.md 是 Markdown 文档，描述技能和工具。工具代码在别处 |
| "Skills 替代 FunctionTool" | 不是替代关系。Skill 是 FunctionTool 的容器和组织方式 |
| "Skills 只能有一个工具" | 可以有一组相关工具。weather-tools skill 就有 3 个工具 |
| "load 后占用 token" | 是的。body 内容会拼到 system prompt。所以延迟加载是性能优化 |
| "Skills 只能本地用" | 也可以远程加载（从 Git repo），支持 Cube/E2B 沙箱执行 |