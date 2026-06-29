# PlateAgent — AI-Enhanced License Plate Recognition

[![Python](https://img.shields.io/badge/Python-3.12-blue)](https://www.python.org/)
[![tRPC-Agent](https://img.shields.io/badge/tRPC--Agent-SDK-green)](https://github.com/trpc-group/trpc-agent-python)
[![License](https://img.shields.io/badge/License-Apache%202.0-orange)](LICENSE)

> 基于 tRPC-Agent GraphAgent 的车牌识别智能体 — 犀牛鸟开源计划 tRPC 方向申报项目

## Overview

PlateAgent is a production-oriented license plate recognition system built with **tRPC-Agent SDK**. It demonstrates the full Agent engineering lifecycle: tool definition, graph orchestration, RAG knowledge base, streaming service, evaluation system, and observability.

```
User Image → Preprocess → Locate → Segment → Parallel SVM → {Human Review | LLM Verify} → Output
                                                              │
                                              ChromaDB RAG ──┘  (blacklist + confusion chars)
```

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    FastAPI Server (:8000)                │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │ /api/chat    │  │/api/recognize│  │ /api/health  │  │
│  │  SSE Stream  │  │  SSE Stream  │  │              │  │
│  └──────┬───────┘  └──────┬───────┘  └──────────────┘  │
│         │                 │                              │
│         ▼                 ▼                              │
│  ┌─────────────┐  ┌──────────────────────────────┐      │
│  │  LlmAgent   │  │       GraphAgent (6 nodes)    │      │
│  │  (chat)     │  │  preprocess → locate → segment│      │
│  │             │  │  → recognize(parallel) →      │      │
│  │             │  │  {human_review|llm_verify}    │      │
│  │             │  │  → format_output              │      │
│  └─────────────┘  └──────────┬───────────────────┘      │
│                              │                           │
│         ┌────────────────────┼────────────────────┐      │
│         ▼                    ▼                    ▼      │
│  ┌──────────┐  ┌──────────────────┐  ┌────────────────┐ │
│  │ Session  │  │  ChromaDB RAG    │  │  OpenTelemetry │ │
│  │ + Memory │  │  (blacklist +    │  │  + TokenTracker│ │
│  │ (Redis)  │  │   confusion)     │  │                │ │
│  └──────────┘  └──────────────────┘  └────────────────┘ │
└─────────────────────────────────────────────────────────┘
```

## Key Features

### Agent Pipeline (6-stage GraphAgent)
| Stage | Node | Method |
|-------|------|--------|
| 1. Preprocess | `preprocess_node` | Gaussian blur → grayscale → Otsu binarize → Canny edge → affine correction |
| 2. Locate | `locate_node` | Morphological + HSV color-based license plate localization |
| 3. Segment | `segment_node` | Vertical projection character segmentation |
| 4. Recognize | `recognize_node` | **Parallel SVM** (HOG features, 99.5% accuracy, 185x speedup) |
| 5. Verify | `llm_verify_node` | LLM re-verification with ChromaDB confusion-char RAG + retry/fallback |
| 5b. Human | `human_review_node` | Interrupt for human confirmation on very-low-confidence chars |
| 6. Output | `format_output_node` | Plate formatting + blacklist lookup + low-confidence annotations |

### Anti-Hallucination System (4-layer defense)
```
Layer 1: SVM confidence >= 0.85 → pass directly
Layer 2: 0.5 <= conf < 0.85 → LLM re-verify (3x retry + timeout + fallback)
Layer 3: LLM all failed → fallback to SVM result
Layer 4: conf < 0.5 → human interrupt + [?] annotation
```

### Engineering Highlights
- **12 FunctionTools**: Preprocessing, localization, segmentation, recognition, knowledge retrieval
- **ChromaDB RAG**: 3 collections (blacklist, plate specs, confusion chars)
- **Session & Memory**: InMemory/Redis switchable via `USE_REDIS=true`
- **SSE Streaming**: FastAPI + AG-UI `AsyncEventWriter` for real-time pipeline progress
- **Evaluation Suite**: 30-image dataset (clear/blur/tilt/noise) + LLM Judge 3D scoring
- **Observability**: OpenTelemetry tracing (`@trace_node`) + Token usage tracking + cost estimation
- **Fault Tolerance**: `tenacity` retry (exponential backoff) + `asyncio.timeout` + graceful degradation
- **Skills System**: `SKILL.md` based skill packaging with lazy loading
- **Parallel Processing**: `asyncio.gather` + `ThreadPoolExecutor` for concurrent character recognition

## Quick Start

### Prerequisites
- Python 3.12+
- DeepSeek API key ([get one here](https://platform.deepseek.com/))

### Installation

```bash
git clone https://github.com/woshidage77/plate-agent.git
cd plate-agent

# Create virtual environment
python -m venv .venv
.venv\Scripts\activate  # Windows
# source .venv/bin/activate  # macOS/Linux

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env: set DEEPSEEK_API_KEY=sk-your-key
```

### Train SVM Model

```bash
python -m agent.tools.train_svm
# Output: 5544 samples, 99.5% test accuracy
```

### Start Server

```bash
python -m server.main
# Server running at http://localhost:8000
# API docs at http://localhost:8000/docs
```

### Run Evaluation

```bash
# Basic evaluation (5 images)
python -m eval.main --limit 5

# With LLM Judge
python -m eval.main --limit 5 --judge --output report.md
```

## Project Structure

```
plate-agent/
├── agent/                      # Agent core
│   ├── config.py               # Model configuration
│   ├── graph_agent.py          # GraphAgent assembly + routing
│   ├── graph_nodes.py          # 7 node functions
│   ├── graph_state.py          # PlateState (TypedDict)
│   ├── llm_agent.py            # LlmAgent (chat entry)
│   ├── session_manager.py      # Session + Memory factory
│   ├── telemetry.py            # OpenTelemetry + @trace_node
│   ├── token_tracker.py        # Token counting + cost
│   ├── retry.py                # LLM retry + timeout + fallback
│   ├── skill_loader.py         # SKILL.md parser
│   ├── tools/                  # 12 FunctionTools
│   │   ├── preprocess.py       # 5 preprocessing tools
│   │   ├── locate.py           # 2 localization tools
│   │   ├── segment.py          # Vertical projection
│   │   ├── recognize.py        # SVM + LLM verify
│   │   ├── knowledge.py        # Blacklist + confusion RAG
│   │   └── train_svm.py        # SVM training script
│   └── knowledge/              # ChromaDB loader
│       └── loader.py
├── server/                     # FastAPI service layer
│   ├── app.py                  # App factory + FastAPIInstrumentor
│   ├── dependencies.py         # Runner singleton + DI
│   ├── schemas.py              # Pydantic models
│   ├── main.py                 # uvicorn entry
│   └── routes/
│       ├── chat.py             # /api/chat SSE stream
│       └── recognize.py        # /api/recognize SSE stream
├── eval/                       # Evaluation system
│   ├── evaluator.py            # Batch evaluation engine
│   ├── judge.py                # LLM Judge (3D scoring)
│   ├── report.py               # Markdown report generator
│   ├── main.py                 # Eval entry
│   └── dataset/                # 30 test images + ground truth
├── skills/                     # Skills system (Day 10)
│   └── plate_recognition/
│       └── SKILL.md
├── docs/                       # Learning notes (3-track system)
│   ├── DayX-A-*.md             # Framework concepts (exam prep)
│   ├── DayX-B-*.md             # Build process
│   ├── DayX-保姆级详解.md       # Beginner-friendly tutorials
│   ├── Day10-A-考试冲刺-全考点映射.md
│   ├── Day10-B-考试冲刺-自测题与口述框架.md
│   └── 项目上下文.md
├── requirements.txt
├── .env.example
└── README.md
```

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Agent Framework | tRPC-Agent SDK (GraphAgent + LlmAgent) |
| LLM | DeepSeek Chat (OpenAI-compatible) |
| Vision | OpenCV 4.8 + scikit-learn (SVM) |
| Vector DB | ChromaDB (RAG knowledge base) |
| Server | FastAPI + SSE streaming |
| Observability | OpenTelemetry (Console + OTLP) |
| Fault Tolerance | tenacity (retry) + asyncio.timeout |
| Session/Memory | InMemory / Redis |

## Learning Notes

This project was built as a 11-day learning sprint. Each day has 3 notes:
- **A (Framework)**: Core concepts for the tRPC-Agent certification exam
- **B (Build)**: Step-by-step build process
- **保姆级 (Tutorial)**: Zero-to-one concept explanations with analogies

See [docs/](docs/) for the complete collection.

## License

This project is part of the [Tencent Rhino-Bird Open Source Program](https://opensource.tencent.com/) application.

---

**Author**: Zhang Zhenghao | [GitHub](https://github.com/woshidage77)