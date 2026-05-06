# PathMind

A multi-agent pathology copilot that delivers a CAP-format second-read report in 60 seconds.

## What it does

PathMind ingests a pathology case (up to 12 whole-slide images), routes it through six cooperating LLM agents, and produces a College of American Pathologists (CAP) format report. The wow moment: two histopathologist agents (Qwen2.5-72B and Meditron-70B) run concurrently on the **same** AMD MI300X GPU, each reads the slides independently, and a Chief agent arbitrates their disagreements through an explicit RCP-style debate before signing the report.

## Why it matters

Pathology second-opinion turnaround averages 8 to 12 days in most health systems, and rural hospitals often have no second pathologist on staff at all. Diagnostic discordance on cancer cases sits between 5 and 10 percent, and disagreement matters most exactly when a single reader is overloaded. PathMind compresses that loop to about 60 seconds, surfaces the disagreement instead of hiding it, and grounds every claim in retrieved literature.

## Demo

Live: https://165-245-134-97.nip.io

![demo](docs/demo.gif)

## Architecture

```
                     +-------------------+
   12 WSI tiles ---> |   Tile Triage     |  rank by suspicious regions
                     +---------+---------+
                               |
                ---------------+---------------
                |                             |
       +--------v--------+           +--------v--------+
       |   Histo-A       |           |   Histo-B       |
       |   Qwen2.5-72B   |           |   Meditron-70B  |
       |   (port 8001)   |           |   (port 8002)   |
       +--------+--------+           +--------+--------+
                |                             |
                +--------------+--------------+
                               |
                     +---------v---------+
                     |   CrossSlide      |  reconcile per-slide findings
                     +---------+---------+
                               |
                     +---------v---------+
                     | Literature Hunter |  Qdrant RAG (PubMed + TCGA)
                     +---------+---------+
                               |
                     +---------v---------+
                     |   Chief           |  RCP debate -> CAP report
                     +-------------------+
```

WebSocket streaming pushes every agent's tool calls and intermediate reasoning to the UI as it happens.

## Multi-model on MI300X

Both 70B+ models live on a single 192GB HBM3 GPU at the same time:

| Model | VRAM | Port | GPU util | Agents |
|---|---|---|---|---|
| Qwen2.5-72B-Instruct | ~144 GB | 8001 | 0.55 | Histo-A, CrossSlide, Literature Hunter, Chief |
| Meditron-70B | ~140 GB | 8002 | 0.40 | Histo-B |

Constrained `gpu_memory_utilization` (0.55 + 0.40 = 0.95 of 192GB) keeps both vLLM instances resident with KV cache headroom. Source: `backend/vllm_config/models.yaml`.

## Stack

- **Backend**: Python 3.11 + FastAPI + WebSocket streaming
- **Frontend**: Next.js 16 + Tailwind + shadcn (PWA installable)
- **LLM**: Qwen2.5-72B-Instruct + Meditron-70B served via vLLM (OpenAI-compat). Anthropic Claude SDK for local dev fallback. Routing in `backend/llm.py`.
- **RAG**: Qdrant collection `pathmind_literature` (48 PubMed abstracts + 7 TCGA seeds), embedded with `sentence-transformers/all-MiniLM-L6-v2`
- **GPU**: AMD MI300X 192GB HBM3 (hackathon droplet)

## Quick start (local dev)

```bash
cd backend && pip install -r requirements.txt && python main.py
cd ../frontend && npm install && npm run dev
```

By default the backend uses the Anthropic SDK for development. Set `ANTHROPIC_API_KEY` in your environment.

## Run on MI300X droplet

```bash
bash backend/vllm_config/start_vllm.sh
```

Wait until both logs (`/tmp/vllm_qwen72b.log`, `/tmp/vllm_meditron70b.log`) report `Application startup complete`, then point the backend at vLLM:

```bash
export LLM_BACKEND=vllm
export VLLM_BASE_URL_QWEN72B=http://localhost:8001/v1
export VLLM_BASE_URL_MEDITRON70B=http://localhost:8002/v1
pm2 restart pathmind-backend --update-env
```

Stop both vLLM instances:

```bash
pkill -f vllm.entrypoints.openai.api_server
```

## Project structure

```
pathmind/
  backend/
    main.py                  FastAPI app + WebSocket endpoint
    llm.py                   Anthropic / vLLM router
    agents/
      tile_triage.py
      histopathologist_a.py  Qwen2.5-72B
      histopathologist_b.py  Meditron-70B
      cross_slide.py
      literature_hunter.py
      chief.py               RCP debate + CAP report
    rag/
      build_index.py         Qdrant index builder
      search.py              retrieval
    vllm_config/
      models.yaml            multi-model VRAM plan
      start_vllm.sh          launcher for both vLLM instances
    schemas/                 pydantic models for agent IO
    prompts/                 system prompts per agent
  frontend/
    app/                     Next.js 16 app router
    components/              shadcn UI + agent stream views
  scripts/
    reality_check.py         hackathon project sanity check
    make_fixture.py          synthetic WSI test cases
  data/                      sample slides + RAG corpus
  docs/                      design notes, demo assets
```

## Built for AMD Advancing AI Hackathon 2026

Submitted to the AMD Advancing AI Hackathon 2026 (May 4 to 10, 2026), MI300X track.
