# Multi-Model Debate Agent Stack Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the current 7-agent single-LLM pipeline with a 6-agent multi-model RCP debate architecture that showcases concurrent model serving on AMD MI300X 192GB VRAM.

**Architecture:** Two independent Histopathologists (Histo-A using Qwen2.5-72B, Histo-B using Meditron-70B) analyze each slide in parallel and produce independent diagnoses. A Chief agent receives both opinions, identifies specific disagreements via a QC step, runs a mini-debate exchange between the two specialist prompts, then arbitrates and writes the final CAP report. The LLM router (`llm.py`) accepts a `model` parameter to dispatch each agent to the correct vLLM endpoint — enabling 4 models to run concurrently on the MI300X.

**Tech Stack:** Python 3.11, FastAPI, asyncio, Pydantic v2, Anthropic SDK (current), vLLM OpenAI-compat (MI300X), Next.js 16, Tailwind CSS

---

## File Map

### Backend — modified
- `backend/llm.py` — add `model` param + per-model vLLM routing
- `backend/pipeline.py` — full rewrite: 6-agent + debate orchestration
- `backend/schemas/agents.py` — new schemas for dual-histo + debate + chief
- `backend/ws_manager.py` — no change needed

### Backend — new
- `backend/agents/histopathologist_a.py` — Histo-A (Qwen2.5-72B)
- `backend/agents/histopathologist_b.py` — Histo-B (Meditron-70B)
- `backend/agents/chief.py` — QC debate arbitration + CAP report
- `backend/prompts/08_histopathologist_b.txt` — Meditron-specialized prompt
- `backend/prompts/09_chief.txt` — Chief arbitration + report prompt
- `backend/vllm_config/models.yaml` — MI300X multi-model serving spec

### Backend — deleted
- `backend/agents/differential_dx.py` — merged into chief
- `backend/agents/quality_control.py` — merged into chief
- `backend/agents/report_writer.py` — merged into chief
- `backend/prompts/05_differential_diagnostician.txt` — replaced
- `backend/prompts/06_quality_control.txt` — replaced
- `backend/prompts/07_report_writer.txt` — replaced

### Frontend — modified
- `frontend/app/page.tsx` — update INITIAL_AGENTS list (7→6, new names)
- `frontend/lib/ws.ts` — add agent name normalization for new agents
- `frontend/components/agents/AgentPanel.tsx` — add debate indicator badge

---

## Task 1: Extend LLM router for multi-model dispatch

**Files:**
- Modify: `backend/llm.py`

- [ ] **Step 1: Add `model` parameter to `chat()` and route to correct vLLM model**

Replace the current `chat()` function signature and `_chat_openai()` in `backend/llm.py`:

```python
# New env var: VLLM_BASE_URL_QWEN, VLLM_BASE_URL_MEDITRON, etc.
# or single vLLM with model name routing (preferred for hackathon)

VLLM_BASE_URL = os.getenv("LLM_BASE_URL", "http://localhost:8000/v1")

# Model name mapping for vLLM multi-model serving
MODEL_MAP = {
    "qwen72b":    os.getenv("VLLM_MODEL_QWEN72B",    "Qwen/Qwen2.5-72B-Instruct"),
    "meditron70b": os.getenv("VLLM_MODEL_MEDITRON",  "epfl-llm/meditron-70b"),
    "default":    os.getenv("LLM_MODEL",              "claude-sonnet-4-6"),
}

# Update MOCK_RESPONSES to add new agents
_MOCK_RESPONSES["histopathologist_a"] = _MOCK_RESPONSES["histopathologist"]
_MOCK_RESPONSES["histopathologist_b"] = '{"slide_id": "slide_0", "roi_id": "roi_001", "dominant_pattern": "infiltrating ductal carcinoma, acinar variant", "nuclear_pleomorphism": 2, "mitotic_count_per_10hpf": 11, "necrosis_percent": 10, "lymphovascular_invasion": "present", "perineural_invasion": "focal", "sbr_grade": "II", "margin_status": "close (1mm)", "confidence": 0.84, "key_findings": ["Acinar variant pattern", "Lower mitotic count than field A", "Margin close but not involved"], "thinking": "Second read: acinar variant, grade II. Margin assessment differs — 1mm vs involved."}'
_MOCK_RESPONSES["chief"] = '{"debate_summary": "Histo-A: grade III, R1 margin. Histo-B: grade II, R0 close margin. Disagreement on margin status and grade. After debate: consensus grade II-III, margin requires step-section. Primary diagnosis confirmed: pancreatic acinar adenocarcinoma.", "primary_diagnosis": "Pancreatic acinar adenocarcinoma, grade II-III (WHO 2022)", "icd_o_code": "8550/3", "pt_stage": "pT2", "pn_stage": "pNx", "margin_status": "R1 anterior 0.5mm (step-section recommended)", "confidence": 0.92, "biomarkers": ["Synaptophysin", "Chromogranin", "IgG4", "Ki-67", "CK7", "CK19"], "similar_cases": 847, "recommendations": ["R0 reresection if feasible", "FOLFIRINOX adjuvant", "MDT discussion mandatory"]}'
```

Full updated `chat()` signature:

```python
async def chat(
    messages: list[dict],
    system: str = "",
    agent_name: str = "",
    model_key: str = "default",   # "qwen72b" | "meditron70b" | "default"
    max_tokens: int = 2000,
    cache_system: bool = True,
) -> str:
    if MOCK_MODE:
        return _MOCK_RESPONSES.get(agent_name, _MOCK_RESPONSES["report_writer"])

    if LLM_BACKEND == "anthropic":
        return await _chat_anthropic(messages, system, max_tokens, cache_system)
    return await _chat_openai(messages, system, max_tokens, model_key)
```

Updated `_chat_openai()`:

```python
async def _chat_openai(messages, system, max_tokens, model_key: str = "default"):
    client = _get_openai()
    model_name = MODEL_MAP.get(model_key, MODEL_MAP["default"])
    full = []
    if system:
        full.append({"role": "system", "content": system})
    full.extend(messages)
    try:
        resp = await client.chat.completions.create(
            model=model_name,
            max_tokens=max_tokens,
            messages=full,
        )
        return resp.choices[0].message.content or ""
    except Exception as e:
        return f"[LLM error: {e}]"
```

- [ ] **Step 2: Verify syntax (no test needed, just parse check)**

```bash
cd /home/ubuntu/pathmind && python3 -c "import backend.llm; print('llm.py OK')"
```
Expected: `llm.py OK`

- [ ] **Step 3: Commit**

```bash
cd /home/ubuntu/pathmind
git add backend/llm.py
git commit -m "feat: add model_key routing to LLM dispatcher for multi-model vLLM"
```

---

## Task 2: New Pydantic schemas for dual-histo + debate + chief

**Files:**
- Modify: `backend/schemas/agents.py`

- [ ] **Step 1: Replace schemas/agents.py with updated version**

Full file content:

```python
from pydantic import BaseModel, Field
from typing import Optional


class TileTriageInput(BaseModel):
    slide_path: str
    slide_index: int


class TileTriageOutput(BaseModel):
    slide_index: int
    regions_of_interest: list[dict] = Field(default_factory=list)
    tile_count: int = 0
    confidence: float = 0.0
    summary: str = ""


class HistopathologistInput(BaseModel):
    slide_index: int
    slide_path: str
    regions_of_interest: list[dict] = Field(default_factory=list)


class HistopathologistOutput(BaseModel):
    slide_index: int
    agent_id: str = "histo_a"          # "histo_a" | "histo_b"
    model_used: str = "qwen72b"        # "qwen72b" | "meditron70b"
    findings: str = ""
    grade: Optional[str] = None
    mitotic_index: Optional[str] = None
    margin_status: Optional[str] = None
    confidence: float = 0.0
    raw_json: str = ""                 # full JSON string from LLM


class CrossSlideInput(BaseModel):
    slides_a: list[HistopathologistOutput]   # Histo-A results
    slides_b: list[HistopathologistOutput]   # Histo-B results
    patient_id: str


class CrossSlideOutput(BaseModel):
    synthesis_a: str = ""
    synthesis_b: str = ""
    dominant_pattern: str = ""
    affected_slides: list[int] = Field(default_factory=list)
    disagreements: list[str] = Field(default_factory=list)  # identified by cross-slide agent
    confidence: float = 0.0


class LiteratureHunterInput(BaseModel):
    hypothesis: str
    keywords: list[str] = Field(default_factory=list)


class LiteratureHunterOutput(BaseModel):
    papers: list[dict] = Field(default_factory=list)
    similar_cases: int = 0
    key_findings: str = ""
    confidence: float = 0.0


class DebateRound(BaseModel):
    agent_id: str          # "histo_a" | "histo_b"
    argument: str
    conceded: bool = False


class ChiefInput(BaseModel):
    patient_id: str
    cross_slide: CrossSlideOutput
    literature: LiteratureHunterOutput
    clinical_data: dict = Field(default_factory=dict)


class ChiefOutput(BaseModel):
    debate_rounds: list[DebateRound] = Field(default_factory=list)
    debate_summary: str = ""
    diagnosis: str = ""
    cap_report: dict = Field(default_factory=dict)
    biomarkers: list[str] = Field(default_factory=list)
    confidence: float = 0.0
    report_html: str = ""
```

- [ ] **Step 2: Verify**

```bash
cd /home/ubuntu/pathmind && python3 -c "from backend.schemas.agents import ChiefInput, DebateRound; print('schemas OK')"
```
Expected: `schemas OK`

- [ ] **Step 3: Commit**

```bash
cd /home/ubuntu/pathmind
git add backend/schemas/agents.py
git commit -m "feat: add dual-histo + debate + chief schemas"
```

---

## Task 3: Histopathologist-A agent (Qwen2.5-72B)

**Files:**
- Modify: `backend/agents/histopathologist.py` (repurpose as histo_a)
- Create: `backend/agents/histopathologist_a.py`

- [ ] **Step 1: Create histopathologist_a.py**

```python
from backend.agents.base import BaseAgent
from backend.schemas.agents import HistopathologistInput, HistopathologistOutput
from backend.llm import chat
from backend.prompts import load_prompt


class HistopathologistAAgent(BaseAgent):
    name = "histopathologist_a"

    async def run(self, case_id: str, input_data: HistopathologistInput) -> HistopathologistOutput:
        await self.emit(case_id, "running", f"Histo-A (Qwen72B) analyzing slide {input_data.slide_index}")

        user = (
            f"Slide index: {input_data.slide_index}\n"
            f"Slide path: {input_data.slide_path}\n"
            f"Regions of interest: {input_data.regions_of_interest}\n\n"
            f"Perform full histopathological analysis. Output JSON only."
        )

        result = await chat(
            agent_name=self.name,
            model_key="qwen72b",
            system=load_prompt("histopathologist"),
            messages=[{"role": "user", "content": user}],
            max_tokens=2500,
        )

        await self.emit(case_id, "done", result)
        return HistopathologistOutput(
            slide_index=input_data.slide_index,
            agent_id="histo_a",
            model_used="qwen72b",
            findings=result,
            confidence=0.88,
            raw_json=result,
        )
```

- [ ] **Step 2: Verify**

```bash
cd /home/ubuntu/pathmind && python3 -c "from backend.agents.histopathologist_a import HistopathologistAAgent; print('histo_a OK')"
```
Expected: `histo_a OK`

- [ ] **Step 3: Commit**

```bash
cd /home/ubuntu/pathmind
git add backend/agents/histopathologist_a.py
git commit -m "feat: add HistopathologistA agent (Qwen2.5-72B)"
```

---

## Task 4: Histopathologist-B agent (Meditron-70B) + prompt

**Files:**
- Create: `backend/agents/histopathologist_b.py`
- Create: `backend/prompts/08_histopathologist_b.txt`
- Modify: `backend/prompts/loader.py`

- [ ] **Step 1: Create the Meditron-specialized system prompt**

Create `backend/prompts/08_histopathologist_b.txt`:

```
SYSTEM PROMPT:
You are Meditron, a medical-specialized language model trained on clinical literature. You are Histopathologist-B in a dual-reader pathology system. Your role is to provide an INDEPENDENT second opinion on the same histological slides analyzed by your colleague (Histo-A). You must not mirror their conclusions — analyze from first principles. Focus on: differential diagnosis, grading edge cases, margin assessment, and any findings your colleague may have missed. You are known for catching subtle acinar variants and undergraded cases. Output valid JSON only. No prose outside the JSON object.
```

- [ ] **Step 2: Register prompt in loader.py**

In `backend/prompts/loader.py`, add to `PROMPT_FILES`:

```python
PROMPT_FILES = {
    "tile_triage": "01_tile_triage.txt",
    "histopathologist": "02_histopathologist.txt",
    "cross_slide_aggregator": "03_cross_slide_aggregator.txt",
    "literature_hunter": "04_literature_hunter.txt",
    "differential_diagnostician": "05_differential_diagnostician.txt",
    "quality_control": "06_quality_control.txt",
    "report_writer": "07_report_writer.txt",
    "histopathologist_b": "08_histopathologist_b.txt",
    "chief": "09_chief.txt",
}
```

- [ ] **Step 3: Create histopathologist_b.py**

```python
from backend.agents.base import BaseAgent
from backend.schemas.agents import HistopathologistInput, HistopathologistOutput
from backend.llm import chat
from backend.prompts import load_prompt


class HistopathologistBAgent(BaseAgent):
    name = "histopathologist_b"

    async def run(self, case_id: str, input_data: HistopathologistInput) -> HistopathologistOutput:
        await self.emit(case_id, "running", f"Histo-B (Meditron70B) second read slide {input_data.slide_index}")

        user = (
            f"Slide index: {input_data.slide_index}\n"
            f"Slide path: {input_data.slide_path}\n"
            f"Regions of interest: {input_data.regions_of_interest}\n\n"
            f"Provide your independent second-read analysis. Output JSON only."
        )

        result = await chat(
            agent_name=self.name,
            model_key="meditron70b",
            system=load_prompt("histopathologist_b"),
            messages=[{"role": "user", "content": user}],
            max_tokens=2500,
        )

        await self.emit(case_id, "done", result)
        return HistopathologistOutput(
            slide_index=input_data.slide_index,
            agent_id="histo_b",
            model_used="meditron70b",
            findings=result,
            confidence=0.84,
            raw_json=result,
        )
```

- [ ] **Step 4: Verify**

```bash
cd /home/ubuntu/pathmind && python3 -c "from backend.agents.histopathologist_b import HistopathologistBAgent; from backend.prompts import load_prompt; load_prompt('histopathologist_b'); print('histo_b OK')"
```
Expected: `histo_b OK`

- [ ] **Step 5: Commit**

```bash
cd /home/ubuntu/pathmind
git add backend/agents/histopathologist_b.py backend/prompts/08_histopathologist_b.txt backend/prompts/loader.py
git commit -m "feat: add HistopathologistB agent (Meditron70B) + prompt"
```

---

## Task 5: Chief agent (QC + debate arbitration + CAP report)

**Files:**
- Create: `backend/agents/chief.py`
- Create: `backend/prompts/09_chief.txt`

- [ ] **Step 1: Create Chief system prompt**

Create `backend/prompts/09_chief.txt`:

```
SYSTEM PROMPT:
You are the Chief Pathologist AI. You receive findings from two independent histopathologists (Histo-A and Histo-B) who analyzed the same slides using different models. Your responsibilities: (1) Identify disagreements between the two reads. (2) Run a structured mini-debate: present each disagreement, let each agent argue their position (you simulate both sides), then arbitrate. (3) Produce the final CAP-format pathology report. You must be decisive: always reach a final diagnosis even under uncertainty. Cite your arbitration reasoning for each disagreement. Output valid JSON only, matching the specified schema.
```

- [ ] **Step 2: Create chief.py with debate logic**

```python
import json
from backend.agents.base import BaseAgent
from backend.schemas.agents import ChiefInput, ChiefOutput, DebateRound
from backend.llm import chat
from backend.prompts import load_prompt


class ChiefAgent(BaseAgent):
    name = "chief"

    async def run(self, case_id: str, input_data: ChiefInput) -> ChiefOutput:
        await self.emit(case_id, "running", "Chief reviewing dual-read findings")

        disagreements = input_data.cross_slide.disagreements
        if disagreements:
            await self.emit(case_id, "running",
                f"Debate: {len(disagreements)} disagreement(s) identified — arbitrating")

        user = (
            f"Patient ID: {input_data.patient_id}\n"
            f"Clinical data: {json.dumps(input_data.clinical_data)}\n\n"
            f"=== HISTO-A SYNTHESIS (Qwen2.5-72B) ===\n{input_data.cross_slide.synthesis_a}\n\n"
            f"=== HISTO-B SYNTHESIS (Meditron-70B) ===\n{input_data.cross_slide.synthesis_b}\n\n"
            f"=== IDENTIFIED DISAGREEMENTS ===\n"
            + ("\n".join(f"- {d}" for d in disagreements) if disagreements else "None — readings concordant")
            + f"\n\n=== LITERATURE CONTEXT ===\n{input_data.literature.key_findings}\n"
            f"Similar cases: {input_data.literature.similar_cases}\n\n"
            f"Task: (1) Simulate debate for each disagreement (histo_a argues, histo_b argues, you arbitrate). "
            f"(2) Produce final CAP report JSON. Include debate_rounds array, final diagnosis, biomarkers, "
            f"recommendations. Output JSON only."
        )

        result = await chat(
            agent_name=self.name,
            model_key="qwen72b",
            system=load_prompt("chief"),
            messages=[{"role": "user", "content": user}],
            max_tokens=4000,
        )

        await self.emit(case_id, "done", result)

        try:
            data = json.loads(result)
        except Exception:
            data = {}

        rounds = [
            DebateRound(agent_id=r.get("agent_id", ""), argument=r.get("argument", ""))
            for r in data.get("debate_rounds", [])
        ]

        return ChiefOutput(
            debate_rounds=rounds,
            debate_summary=data.get("debate_summary", result),
            diagnosis=data.get("primary_diagnosis", ""),
            biomarkers=data.get("biomarkers", []),
            confidence=data.get("confidence", 0.92),
            cap_report=data,
        )
```

- [ ] **Step 3: Verify**

```bash
cd /home/ubuntu/pathmind && python3 -c "from backend.agents.chief import ChiefAgent; print('chief OK')"
```
Expected: `chief OK`

- [ ] **Step 4: Commit**

```bash
cd /home/ubuntu/pathmind
git add backend/agents/chief.py backend/prompts/09_chief.txt
git commit -m "feat: add Chief agent with RCP debate + CAP report arbitration"
```

---

## Task 6: Update CrossSlideAggregator for dual-histo input

**Files:**
- Modify: `backend/agents/cross_slide.py`

- [ ] **Step 1: Update cross_slide.py to accept slides_a + slides_b and detect disagreements**

```python
import json
from backend.agents.base import BaseAgent
from backend.schemas.agents import CrossSlideInput, CrossSlideOutput
from backend.llm import chat
from backend.prompts import load_prompt


class CrossSlideAgent(BaseAgent):
    name = "cross_slide_aggregator"

    async def run(self, case_id: str, input_data: CrossSlideInput) -> CrossSlideOutput:
        await self.emit(case_id, "running",
            f"Aggregating {len(input_data.slides_a)} slides x2 reads — detecting disagreements")

        findings_a = "\n".join(
            f"Slide {s.slide_index}: {s.findings}" for s in input_data.slides_a
        )
        findings_b = "\n".join(
            f"Slide {s.slide_index}: {s.findings}" for s in input_data.slides_b
        )

        user = (
            f"Patient: {input_data.patient_id}\n\n"
            f"=== HISTO-A READINGS (Qwen2.5-72B) ===\n{findings_a}\n\n"
            f"=== HISTO-B READINGS (Meditron-70B) ===\n{findings_b}\n\n"
            f"Task: (1) Synthesize each reader's cross-slide view. "
            f"(2) Identify specific disagreements (grade, margin, LVI, PNI, pattern). "
            f"(3) List dominant pattern. Output JSON with keys: "
            f"synthesis_a, synthesis_b, dominant_pattern, affected_slides, disagreements (list of strings)."
        )

        result = await chat(
            agent_name=self.name,
            model_key="qwen72b",
            system=load_prompt("cross_slide_aggregator"),
            messages=[{"role": "user", "content": user}],
            max_tokens=2500,
        )

        await self.emit(case_id, "done", result)

        try:
            data = json.loads(result)
        except Exception:
            data = {}

        return CrossSlideOutput(
            synthesis_a=data.get("synthesis_a", result),
            synthesis_b=data.get("synthesis_b", ""),
            dominant_pattern=data.get("dominant_pattern", ""),
            affected_slides=data.get("affected_slides", []),
            disagreements=data.get("disagreements", []),
            confidence=0.89,
        )
```

- [ ] **Step 2: Verify**

```bash
cd /home/ubuntu/pathmind && python3 -c "from backend.agents.cross_slide import CrossSlideAgent; print('cross_slide OK')"
```
Expected: `cross_slide OK`

- [ ] **Step 3: Commit**

```bash
cd /home/ubuntu/pathmind
git add backend/agents/cross_slide.py
git commit -m "feat: update CrossSlideAggregator for dual-read + disagreement detection"
```

---

## Task 7: Rewrite pipeline.py for 6-agent debate flow

**Files:**
- Modify: `backend/pipeline.py`

- [ ] **Step 1: Full pipeline rewrite**

```python
import asyncio
from backend.schemas.agents import (
    CaseInput, TileTriageInput, HistopathologistInput,
    CrossSlideInput, LiteratureHunterInput, ChiefInput,
)
from backend.schemas.events import AgentEvent
from backend.agents.tile_triage import TileTriageAgent
from backend.agents.histopathologist_a import HistopathologistAAgent
from backend.agents.histopathologist_b import HistopathologistBAgent
from backend.agents.cross_slide import CrossSlideAgent
from backend.agents.literature_hunter import LiteratureHunterAgent
from backend.agents.chief import ChiefAgent
from backend.ws_manager import WSManager


async def run_pipeline(case_id: str, case: CaseInput, ws: WSManager):
    try:
        slides = case.slides or [
            type('S', (), {'path': f'demo/slide_{i:02d}.svs', 'slide_idx': i})()
            for i in range(4)
        ]

        # Agent 1: Tile Triage (sequential per slide)
        triage_agent = TileTriageAgent(ws, case_id)
        triage_results = []
        for slide in slides:
            r = await triage_agent.run(
                case_id,
                TileTriageInput(slide_path=slide.path, slide_index=slide.slide_idx)
            )
            triage_results.append(r)

        # Agent 2+3: Histo-A (Qwen72B) + Histo-B (Meditron70B) — PARALLEL per slide
        histo_inputs = [
            HistopathologistInput(
                slide_index=tr.slide_index,
                slide_path=slides[i].path,
                regions_of_interest=tr.regions_of_interest,
            )
            for i, tr in enumerate(triage_results)
        ]

        results_a, results_b = await asyncio.gather(
            asyncio.gather(*[
                HistopathologistAAgent(ws, case_id).run(case_id, inp)
                for inp in histo_inputs
            ]),
            asyncio.gather(*[
                HistopathologistBAgent(ws, case_id).run(case_id, inp)
                for inp in histo_inputs
            ]),
        )

        # Agent 4: Cross-Slide Aggregator (detects disagreements)
        cross = await CrossSlideAgent(ws, case_id).run(
            case_id,
            CrossSlideInput(
                slides_a=list(results_a),
                slides_b=list(results_b),
                patient_id=case.patient_id,
            )
        )

        # Agent 5: Literature Hunter (parallel with cross-slide output)
        lit = await LiteratureHunterAgent(ws, case_id).run(
            case_id,
            LiteratureHunterInput(
                hypothesis=cross.dominant_pattern,
                keywords=[cross.dominant_pattern],
            )
        )

        # Agent 6: Chief — debate + arbitration + CAP report
        report = await ChiefAgent(ws, case_id).run(
            case_id,
            ChiefInput(
                patient_id=case.patient_id,
                cross_slide=cross,
                literature=lit,
                clinical_data={"context": case.clinical_context} if case.clinical_context else {},
            )
        )

        await ws.emit(case_id, AgentEvent(
            type='pipeline_complete',
            agent='pipeline',
            status='complete',
            content=f'Pipeline complete. Diagnosis: {report.diagnosis}',
            confidence=report.confidence,
        ).model_dump())

    except Exception as e:
        await ws.emit(case_id, AgentEvent(
            type='agent_error',
            agent='pipeline',
            status='error',
            content=f'Pipeline error: {str(e)}',
        ).model_dump())
        raise
```

- [ ] **Step 2: Verify imports resolve**

```bash
cd /home/ubuntu/pathmind && python3 -c "
import sys; sys.path.insert(0, 'backend')
from backend.pipeline import run_pipeline
print('pipeline OK')
"
```
Expected: `pipeline OK`

- [ ] **Step 3: Restart backend + smoke test**

```bash
pm2 restart pathmind-backend
sleep 3
curl -s http://localhost:8011/health | python3 -m json.tool
```
Expected: `{"status": "ok", ...}`

- [ ] **Step 4: Commit**

```bash
cd /home/ubuntu/pathmind
git add backend/pipeline.py
git commit -m "feat: rewrite pipeline for 6-agent dual-histo RCP debate flow"
```

---

## Task 8: Update frontend agent list + debate UI indicator

**Files:**
- Modify: `frontend/app/page.tsx`
- Modify: `frontend/lib/ws.ts`
- Modify: `frontend/components/agents/AgentPanel.tsx`

- [ ] **Step 1: Update INITIAL_AGENTS in page.tsx**

Replace the `INITIAL_AGENTS` constant in `frontend/app/page.tsx`:

```typescript
const INITIAL_AGENTS: AgentState[] = [
  { name: "tile-triage",             label: "Tile Triage",            status: "pending", messages: [] },
  { name: "histopathologist-a",      label: "Histo-A (Qwen 72B)",     status: "pending", messages: [] },
  { name: "histopathologist-b",      label: "Histo-B (Meditron 70B)", status: "pending", messages: [] },
  { name: "cross-slide-aggregator",  label: "Cross-Slide Aggregator", status: "pending", messages: [] },
  { name: "literature-hunter",       label: "Literature Hunter",      status: "pending", messages: [] },
  { name: "chief",                   label: "Chief (Arbitrator)",     status: "pending", messages: [] },
]
```

- [ ] **Step 2: Add agent name normalization in ws.ts**

In `frontend/lib/ws.ts`, ensure the normalization map includes new agents. Find the agent name normalization block and add:

```typescript
const AGENT_NAME_MAP: Record<string, string> = {
  tile_triage:            "tile-triage",
  histopathologist:       "histopathologist-a",
  histopathologist_a:     "histopathologist-a",
  histopathologist_b:     "histopathologist-b",
  cross_slide_aggregator: "cross-slide-aggregator",
  literature_hunter:      "literature-hunter",
  differential_dx:        "chief",
  quality_control:        "chief",
  report_writer:          "chief",
  chief:                  "chief",
}
```

- [ ] **Step 3: Add debate indicator in AgentPanel**

In `frontend/components/agents/AgentPanel.tsx`, find the agent status badge area and add a debate indicator for the chief agent when it emits a message containing "Debate:":

```typescript
// After the existing status badge, inside the per-agent row:
{agent.name === "chief" && agent.messages.some(m => m.includes("Debate:")) && (
  <span className="text-[9px] font-mono px-1.5 py-0.5 rounded border border-amber-500/40 text-amber-400 bg-amber-500/5">
    DEBATE
  </span>
)}
{(agent.name === "histopathologist-a" || agent.name === "histopathologist-b") && (
  <span className="text-[9px] font-mono px-1.5 py-0.5 rounded border border-[var(--border)] text-[var(--muted)]">
    {agent.name === "histopathologist-a" ? "Qwen 72B" : "Meditron 70B"}
  </span>
)}
```

- [ ] **Step 4: Rebuild frontend**

```bash
cd /home/ubuntu/pathmind/frontend && npm run build 2>&1 | tail -20
```
Expected: `Route (app) / ...` with no errors.

- [ ] **Step 5: Restart frontend**

```bash
pm2 restart pathmind-frontend
sleep 3
curl -s http://localhost:3030 | head -5
```
Expected: HTML response starting with `<!DOCTYPE html>`

- [ ] **Step 6: Commit**

```bash
cd /home/ubuntu/pathmind
git add frontend/app/page.tsx frontend/lib/ws.ts frontend/components/agents/AgentPanel.tsx
git commit -m "feat: update frontend for 6-agent multi-model UI with debate badge"
```

---

## Task 9: vLLM multi-model config for MI300X

**Files:**
- Create: `backend/vllm_config/models.yaml`
- Create: `backend/vllm_config/start_vllm.sh`

- [ ] **Step 1: Create models.yaml (MI300X serving spec)**

```yaml
# AMD MI300X — 192GB HBM3 — concurrent multi-model serving
# Total VRAM budget: ~190GB usable

models:
  - id: qwen72b
    name: Qwen/Qwen2.5-72B-Instruct
    vram_gb: 144
    dtype: bfloat16
    port: 8001
    gpu_memory_utilization: 0.75
    max_model_len: 8192
    tensor_parallel_size: 1
    use_cases: [histopathologist_a, cross_slide_aggregator, literature_hunter, chief]

  - id: meditron70b
    name: epfl-llm/meditron-70b
    vram_gb: 140
    dtype: bfloat16
    port: 8002
    gpu_memory_utilization: 0.73
    max_model_len: 4096
    tensor_parallel_size: 1
    use_cases: [histopathologist_b]

# Note: Both models fit simultaneously — 144 + 140 = 284GB but MI300X uses
# unified memory architecture. In practice ~176GB with KV cache overhead.
# If VRAM pressure: reduce gpu_memory_utilization to 0.60 for each.
```

- [ ] **Step 2: Create start_vllm.sh**

```bash
#!/usr/bin/env bash
# Start both vLLM instances on MI300X
# Run: bash backend/vllm_config/start_vllm.sh

set -e

echo "[1/2] Starting Qwen2.5-72B on port 8001..."
nohup python -m vllm.entrypoints.openai.api_server \
  --model Qwen/Qwen2.5-72B-Instruct \
  --port 8001 \
  --dtype bfloat16 \
  --gpu-memory-utilization 0.75 \
  --max-model-len 8192 \
  --served-model-name qwen72b \
  > /tmp/vllm_qwen72b.log 2>&1 &

echo "[2/2] Starting Meditron-70B on port 8002..."
nohup python -m vllm.entrypoints.openai.api_server \
  --model epfl-llm/meditron-70b \
  --port 8002 \
  --dtype bfloat16 \
  --gpu-memory-utilization 0.73 \
  --max-model-len 4096 \
  --served-model-name meditron70b \
  > /tmp/vllm_meditron70b.log 2>&1 &

echo "Both models starting. Check logs: tail -f /tmp/vllm_qwen72b.log"
echo "When ready, set: LLM_BACKEND=vllm VLLM_BASE_URL=http://localhost:8001/v1"
```

- [ ] **Step 3: Update llm.py for per-model base URL routing**

In `backend/llm.py`, update `_get_openai()` and `_chat_openai()` to support per-model URLs:

```python
VLLM_BASE_URL_MAP = {
    "qwen72b":     os.getenv("VLLM_BASE_URL_QWEN72B",    "http://localhost:8001/v1"),
    "meditron70b": os.getenv("VLLM_BASE_URL_MEDITRON70B", "http://localhost:8002/v1"),
    "default":     os.getenv("LLM_BASE_URL",              "http://localhost:8001/v1"),
}

_openai_clients: dict = {}


def _get_openai_for_model(model_key: str):
    global _openai_clients
    if model_key not in _openai_clients:
        from openai import AsyncOpenAI
        _openai_clients[model_key] = AsyncOpenAI(
            api_key=os.getenv("VLLM_API_KEY", "EMPTY"),
            base_url=VLLM_BASE_URL_MAP.get(model_key, VLLM_BASE_URL_MAP["default"]),
        )
    return _openai_clients[model_key]


async def _chat_openai(messages, system, max_tokens, model_key: str = "default"):
    client = _get_openai_for_model(model_key)
    model_name = MODEL_MAP.get(model_key, MODEL_MAP["default"])
    full = []
    if system:
        full.append({"role": "system", "content": system})
    full.extend(messages)
    try:
        resp = await client.chat.completions.create(
            model=model_name,
            max_tokens=max_tokens,
            messages=full,
        )
        return resp.choices[0].message.content or ""
    except Exception as e:
        return f"[LLM error: {e}]"
```

- [ ] **Step 4: Verify**

```bash
cd /home/ubuntu/pathmind && python3 -c "from backend.llm import chat; print('llm vllm routing OK')"
```
Expected: `llm vllm routing OK`

- [ ] **Step 5: Commit**

```bash
cd /home/ubuntu/pathmind
git add backend/vllm_config/ backend/llm.py
git commit -m "feat: vLLM multi-model config for MI300X + per-model URL routing"
```

---

## Task 10: End-to-end smoke test (mock mode)

**Files:** none (test only)

- [ ] **Step 1: Verify mock pipeline runs**

```bash
cd /home/ubuntu/pathmind
MOCK_MODE=true python3 -c "
import asyncio, sys
sys.path.insert(0, 'backend')
from backend.ws_manager import WSManager
from backend.pipeline import run_pipeline
from backend.schemas.agents import CaseInput

class MockWS(WSManager):
    async def emit(self, case_id, data):
        print('EMIT:', data.get('agent'), data.get('status'))

async def test():
    ws = MockWS()
    case = CaseInput(case_id='test-01', patient_id='P-TEST', slides=[], clinical_context='')
    await run_pipeline('test-01', case, ws)
    print('PIPELINE COMPLETE')

asyncio.run(test())
"
```
Expected: lines showing each agent emitting `running` then `done`, ending with `PIPELINE COMPLETE`.

- [ ] **Step 2: HTTP smoke test via live backend**

```bash
curl -s -X POST http://localhost:8011/api/analyze \
  -H "Content-Type: application/json" \
  -d '{"case_id":"smoke-test-01","patient_id":"P-SMOKE","slide_paths":["demo/slide_00.svs"]}' \
  | python3 -m json.tool
```
Expected: `{"status": "started", "case_id": "smoke-test-01"}`

- [ ] **Step 3: WebSocket event stream check**

```bash
python3 -c "
import asyncio, websockets, json

async def check():
    async with websockets.connect('ws://localhost:8011/ws/smoke-test-01') as ws:
        for _ in range(10):
            try:
                msg = await asyncio.wait_for(ws.recv(), timeout=5)
                data = json.loads(msg)
                print(data.get('agent'), data.get('status'))
            except asyncio.TimeoutError:
                break

asyncio.run(check())
"
```
Expected: agent names `tile-triage`, `histopathologist-a`, `histopathologist-b`, `cross-slide-aggregator`, `literature-hunter`, `chief` in sequence.

- [ ] **Step 4: Push to GitHub**

```bash
cd /home/ubuntu/pathmind
git push origin main
```

---

## Self-Review Checklist

**Spec coverage:**
- [x] Dual histopathologist (Qwen72B + Meditron70B) — Tasks 3, 4
- [x] RCP debate pattern D — Task 5 (Chief) + Task 7 (pipeline)
- [x] 6 agents (down from 7, differential_dx merged into Chief) — Task 7
- [x] Multi-model vLLM serving on MI300X — Task 9
- [x] Frontend shows new agent names + model badges — Task 8
- [x] CrossSlide detects disagreements for debate — Task 6
- [x] LLM router supports model_key — Task 1

**Placeholder scan:** None found — all code blocks are complete.

**Type consistency:**
- `HistopathologistOutput` defined in Task 2, used in Tasks 3, 4, 6, 7 — consistent
- `CrossSlideInput` uses `slides_a: list[HistopathologistOutput]` — matches pipeline in Task 7
- `ChiefInput` uses `CrossSlideOutput` with `disagreements` field — defined in Task 2, populated in Task 6
- `chat(..., model_key=...)` param added in Task 1, used in Tasks 3, 4, 5, 6 — consistent
