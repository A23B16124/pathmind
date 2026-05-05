# Cloud Deployment Roadmap — MI300X

Roadmap to flip PathMind from mock mode to live MI300X dual-model inference once AMD credits land.

Timeline target: 4-6h from credit unlock to live demo.

---

## Phase 0 — Pre-flight (do BEFORE credits arrive)

- [ ] Confirm vLLM ROCm version compatible with target image
- [ ] Bookmark Qwen2.5-72B-Instruct + Meditron-70B HuggingFace URLs
- [ ] Generate HuggingFace token with read access (for gated repos)
- [ ] Backup current mock-mode demo as `git tag v-demo-mock`
- [ ] Test `start_vllm.sh` syntax locally (dry run)

---

## Phase 1 — Provision (30 min)

1. Spin up MI300X instance (1x MI300X, 192GB VRAM, ROCm 6.x)
2. SSH access + open ports 8001, 8002 (firewall)
3. Install: `git`, `python3.11`, `pip`, `tmux`, `htop`, `rocm-smi`
4. `git clone https://github.com/A23B16124/pathmind`
5. `pip install -r backend/requirements.txt vllm[rocm]`
6. `huggingface-cli login` with token

**Validation:** `rocm-smi` shows MI300X, 192GB free.

---

## Phase 2 — Model Download (60-90 min, parallel)

Both downloads in parallel via tmux:

```bash
# Pane 1
huggingface-cli download Qwen/Qwen2.5-72B-Instruct --local-dir ~/models/qwen72b

# Pane 2
huggingface-cli download epfl-llm/meditron-70b --local-dir ~/models/meditron70b
```

Sizes: Qwen ~145GB, Meditron ~140GB. Total disk ~300GB.

**Validation:** `du -sh ~/models/*` shows both directories full size.

---

## Phase 3 — vLLM Boot (20 min)

Run `bash scripts/start_vllm.sh` (already in repo):
- Qwen72B → port 8001, gpu_memory_utilization=0.55
- Meditron70B → port 8002, gpu_memory_utilization=0.40

Both processes share the same MI300X. Total budget ~95% VRAM (~182GB).

**Validation:**
```bash
curl http://localhost:8001/v1/models  # Qwen
curl http://localhost:8002/v1/models  # Meditron
rocm-smi --showmemuse                 # Should show ~180GB used
```

If OOM: drop gpu_memory_utilization on Meditron to 0.35, re-test.

---

## Phase 4 — Backend Wire-Up (15 min)

On the MI300X box (or wherever backend runs):

```bash
export MOCK_MODE=false
export LLM_BACKEND=vllm
export VLLM_BASE_URL_QWEN72B=http://localhost:8001/v1
export VLLM_BASE_URL_MEDITRON70B=http://localhost:8002/v1
export VLLM_MODEL_QWEN72B=Qwen/Qwen2.5-72B-Instruct
export VLLM_MODEL_MEDITRON=epfl-llm/meditron-70b
```

Restart backend:
```bash
cd /home/ubuntu/pathmind
nohup python3 -m uvicorn backend.main:app --host 0.0.0.0 --port 8011 > /tmp/pathmind.log 2>&1 &
```

**Validation:**
```bash
curl http://localhost:8011/health | jq
# Expect: vllm_models.qwen72b.reachable = true AND meditron70b.reachable = true
```

---

## Phase 5 — End-to-End Smoke Test (15 min)

```bash
curl -X POST http://localhost:8011/api/analyze \
  -H "Content-Type: application/json" \
  -d '{"case_id":"smoke-001","patient_id":"P-TEST","slide_paths":["demo.svs"]}'
```

Watch WebSocket events on frontend. Both Histo-A + Histo-B should fire concurrently (check timestamps in logs).

**Critical checks:**
- All 6 agents emit `agent_done` events
- Cross-slide outputs `disagreements` array (real, not mock)
- Chief outputs `debate_rounds` JSON
- Final `analysis_complete` arrives with structured `report` payload

If parsing fails: check `/tmp/pathmind.log` for fence-stripping errors. Adjust prompts if LLM wraps JSON inconsistently.

---

## Phase 6 — Latency + Tuning (30 min)

Measure end-to-end pipeline latency on 12-slide case:
- Target: < 90s total
- Bottleneck likely Histo-A/B (largest prompts)

Optimizations if too slow:
- Reduce `max_tokens` from 2000 to 1500 on histo agents
- Enable vLLM `--enable-prefix-caching` (already useful for shared system prompts)
- Truncate ROIs context to top-3 per slide

---

## Phase 7 — Frontend Wiring (10 min)

Update `frontend/.env.production`:
```
NEXT_PUBLIC_API_URL=https://api.pathmind.aegisprops.com
NEXT_PUBLIC_WS_URL=wss://api.pathmind.aegisprops.com
```

Reverse proxy via existing nginx → MI300X box (or tunnel via Cloudflare).

Rebuild + redeploy:
```bash
cd frontend && npm run build && pm2 restart pathmind-front
```

**Validation:** open https://pathmind.aegisprops.com, run demo, watch real LLM tokens stream.

---

## Phase 8 — Demo Polish (45 min)

- [ ] Reset demo state: clean DB, seed Dubois case
- [ ] Test full demo path 5x in a row, time each run
- [ ] Record vidéo backup 90s (Remotion or QuickTime + Whisper subs)
- [ ] Verify all 6 agents emit DEBATE badge correctly
- [ ] Confirm CAP report HTML renders cleanly in ReportPanel
- [ ] Test "Full report" button → /report/[id] page

---

## Phase 9 — Pitch Prep (30 min)

- [ ] Pitch écrit (2min ou 5min selon format)
- [ ] Anticipation Q&A (top 5 questions)
- [ ] Backup vidéo téléversée YouTube unlisted + .mp4 local
- [ ] Hotspot téléphone activé
- [ ] Second laptop allumé en backup

---

## Rollback Plan

Si MI300X tombe pendant la démo : `MOCK_MODE=true` + restart backend → mode mock fonctionne déjà, démo continue.

```bash
export MOCK_MODE=true
pkill -f uvicorn && nohup python3 -m uvicorn backend.main:app --host 0.0.0.0 --port 8011 > /tmp/pathmind.log 2>&1 &
```

---

## Time Budget

| Phase | Duration | Cumulative |
|---|---|---|
| 0. Pre-flight | done before | T+0 |
| 1. Provision | 30 min | T+30 |
| 2. Model download | 90 min | T+2h |
| 3. vLLM boot | 20 min | T+2h20 |
| 4. Backend wire | 15 min | T+2h35 |
| 5. E2E smoke | 15 min | T+2h50 |
| 6. Latency tuning | 30 min | T+3h20 |
| 7. Frontend wire | 10 min | T+3h30 |
| 8. Demo polish | 45 min | T+4h15 |
| 9. Pitch prep | 30 min | T+4h45 |

**Total : ~5h cumulative.** Marge de 1h pour debug.

---

## Failure Modes Anticipated

| Symptom | Cause | Fix |
|---|---|---|
| `OOM CUDA` on vLLM boot | gpu_memory_utilization too high | drop Meditron to 0.35 |
| Models reachable=false in /health | port firewall blocked | `ufw allow 8001,8002` |
| Pipeline silent hang | vLLM cold start (first request slow) | pre-warm with curl request |
| JSON parse_failed on Chief | LLM wraps in fences inconsistently | already handled by `_strip_fences` |
| Latency > 120s | network round-trip Vercel→MI300X | colocate backend on MI300X box |
| WebSocket disconnects | nginx proxy timeout | `proxy_read_timeout 300s` |

---

## Definition of Done

- [ ] `/health` shows both vLLM reachable
- [ ] Full demo runs in < 90s with real models
- [ ] Debate badge fires when models actually disagree
- [ ] CAP report HTML renders without missing fields
- [ ] Demo executed 5x cleanly back-to-back
- [ ] Pitch + vidéo backup ready
- [ ] Tag: `git tag v-demo-cloud`
