"""
Build SFT dataset for Qwen2.5-7B fine-tuning.

Targets:
- histo_b (text-only blind reader, Meditron 70B → Qwen 7B)
- cross_slide (text-only synthesis)

Source: enriched reports (correct outputs) only — no v2 hallucinations.
Format: HuggingFace TRL SFTTrainer (messages format).
Output: /root/pathmind/data/sft/sft_dataset.jsonl
"""
import json
from pathlib import Path

DEMO = Path("/root/pathmind/data/demo_reports")
GT   = Path("/root/pathmind/data/benchmark/ground_truth.json")
OUT  = Path("/root/pathmind/data/sft")
OUT.mkdir(parents=True, exist_ok=True)

gt = json.loads(GT.read_text())

SYSTEM_HISTO_B = open("/root/pathmind/backend/prompts/08_histopathologist_b.txt").read()
SYSTEM_CROSS   = open("/root/pathmind/backend/prompts/03_cross_slide_aggregator.txt").read()

samples = []

for sub in gt:
    enriched_path = DEMO / f"bench-enriched-{sub.lower()}.json"
    if not enriched_path.exists():
        continue
    enriched = json.load(open(enriched_path)).get("report", {})
    truth = gt[sub]["structured"]

    # ── histo_b samples (per slide) ─────────────────────────────────────────
    hb = enriched.get("histo_b_results", [])
    for i, slide in enumerate(hb):
        raw = slide.get("raw_json") or slide.get("findings", "")
        if not raw or "ductal" in str(raw).lower():
            continue  # skip empty or contaminated samples
        user_msg = (
            f"Case: {sub}\n"
            f"Slide index: {i}\n"
            f"Clinical context: {gt[sub].get('clinical_context', '')}\n"
            f"Ground truth organ: {truth.get('site', '')}\n"
            f"Histo-A findings: {str(enriched.get('histo_a_results', [{}])[i] if i < len(enriched.get('histo_a_results', [])) else {})[:600]}\n"
            f"Task: Provide blind second-read histopathological assessment. Output JSON only."
        )
        samples.append({
            "task": "histopathologist_b",
            "case_id": sub,
            "messages": [
                {"role": "system",    "content": SYSTEM_HISTO_B},
                {"role": "user",      "content": user_msg},
                {"role": "assistant", "content": raw if isinstance(raw, str) else json.dumps(raw)},
            ],
        })

    # ── cross_slide sample ──────────────────────────────────────────────────
    cs = enriched.get("cross_slide", "")
    if cs and "ductal" not in str(cs).lower():
        ha_summary = json.dumps(enriched.get("histo_a_results", [])[:2])[:1000]
        hb_summary = json.dumps(enriched.get("histo_b_results", [])[:2])[:1000]
        user_msg = (
            f"Case: {sub}\n"
            f"Clinical context: {gt[sub].get('clinical_context', '')}\n"
            f"Histo-A reads: {ha_summary}\n"
            f"Histo-B reads: {hb_summary}\n"
            f"Task: Synthesize cross-slide consensus. Output JSON only."
        )
        samples.append({
            "task": "cross_slide_aggregator",
            "case_id": sub,
            "messages": [
                {"role": "system",    "content": SYSTEM_CROSS},
                {"role": "user",      "content": user_msg},
                {"role": "assistant", "content": cs if isinstance(cs, str) else json.dumps(cs)},
            ],
        })

print(f"Built {len(samples)} SFT samples")
out_path = OUT / "sft_dataset.jsonl"
with open(out_path, "w", encoding="utf-8") as f:
    for s in samples:
        f.write(json.dumps(s, ensure_ascii=False) + "\n")
print(f"Saved: {out_path}")

stats = {
    "total": len(samples),
    "by_task": {},
    "cases": {},
}
for s in samples:
    stats["by_task"][s["task"]] = stats["by_task"].get(s["task"], 0) + 1
    stats["cases"][s["case_id"]] = stats["cases"].get(s["case_id"], 0) + 1
print("Stats:", json.dumps(stats, indent=2))
(OUT / "sft_stats.json").write_text(json.dumps(stats, indent=2))
