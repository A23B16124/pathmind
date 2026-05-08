"""
Build DPO pairs for Qwen2.5-VL-72B fine-tuning.
Format: HuggingFace TRL DPOTrainer (chosen/rejected pairs).
Source:
  - chosen  = enriched reports (correct organ, correct dx)
  - rejected = v2 reports (breast hallucination)
Output: /root/pathmind/data/dpo/dpo_pairs.jsonl
"""
import json
from pathlib import Path

DEMO = Path("/root/pathmind/data/demo_reports")
GT   = Path("/root/pathmind/data/benchmark/ground_truth.json")
OUT  = Path("/root/pathmind/data/dpo")
OUT.mkdir(parents=True, exist_ok=True)

gt = json.loads(GT.read_text())

SYSTEM_HISTO = open("/root/pathmind/backend/prompts/02_histopathologist.txt").read()
SYSTEM_DDX   = open("/root/pathmind/backend/prompts/05_differential_diagnostician.txt").read()

pairs = []

for sub in gt:
    enriched_path = DEMO / f"bench-enriched-{sub.lower()}.json"
    v2_path       = DEMO / f"bench-{sub.lower()}.json"
    if not enriched_path.exists() or not v2_path.exists():
        continue

    enriched = json.load(open(enriched_path)).get("report", {})
    v2       = json.load(open(v2_path)).get("report", {})

    truth = gt[sub]["structured"]
    truth_dx = truth.get("primary_diagnosis", "")

    # ── Histopathologist pairs (per slide) ──────────────────────────────────
    ha_e = enriched.get("histo_a_results", [])
    ha_v = v2.get("histo_a_results", [])

    for i, (e_slide, v_slide) in enumerate(zip(ha_e, ha_v)):
        e_raw = e_slide.get("raw_json") or e_slide.get("findings", "")
        v_raw = v_slide.get("raw_json") or v_slide.get("findings", "")

        # Only keep pairs where rejected has breast hallucination
        if "ductal" not in str(v_raw).lower() and "breast" not in str(v_raw).lower():
            continue

        # Build a minimal user message (we don't have the original prompt, so reconstruct)
        user_msg = (
            f"Case: {sub}\n"
            f"Slide index: {i}\n"
            f"Clinical context: {gt[sub].get('clinical_context', 'Not provided')}\n"
            f"Ground truth organ: {truth.get('site', 'unknown')}\n"
            f"Task: Perform detailed histopathological analysis. Output JSON only."
        )

        pairs.append({
            "type": "histopathologist",
            "case_id": sub,
            "slide_index": i,
            "prompt": [
                {"role": "system", "content": SYSTEM_HISTO},
                {"role": "user",   "content": user_msg},
            ],
            "chosen":   e_raw if isinstance(e_raw, str) else json.dumps(e_raw),
            "rejected": v_raw if isinstance(v_raw, str) else json.dumps(v_raw),
            "ground_truth_dx": truth_dx,
        })

    # ── Differential-Diagnostician pairs ────────────────────────────────────
    e_dx = enriched.get("diagnosis", "")
    v_dx = v2.get("diagnosis", "")

    if e_dx and v_dx and "ductal" in v_dx.lower():
        user_msg = (
            f"Case: {sub}\n"
            f"Clinical context: {gt[sub].get('clinical_context', 'Not provided')}\n"
            f"Histopathologist findings summary: {str(enriched.get('cross_slide', ''))[:400]}\n"
            f"Ground truth organ: {truth.get('site', 'unknown')}\n"
            f"Task: Provide differential diagnosis. Output JSON only."
        )
        pairs.append({
            "type": "differential_dx",
            "case_id": sub,
            "prompt": [
                {"role": "system", "content": SYSTEM_DDX},
                {"role": "user",   "content": user_msg},
            ],
            "chosen":   json.dumps({"primary_diagnosis": e_dx, "confidence": enriched.get("confidence", 0.9)}),
            "rejected": json.dumps({"primary_diagnosis": v_dx, "confidence": v2.get("confidence", 0.5)}),
            "ground_truth_dx": truth_dx,
        })

print(f"Built {len(pairs)} DPO pairs")

# Save JSONL
dpo_path = OUT / "dpo_pairs.jsonl"
with open(dpo_path, "w", encoding="utf-8") as f:
    for p in pairs:
        f.write(json.dumps(p, ensure_ascii=False) + "\n")
print(f"Saved: {dpo_path}")

# Also save stats
stats = {
    "total_pairs": len(pairs),
    "by_type": {},
    "cases": {}
}
for p in pairs:
    t = p["type"]
    stats["by_type"][t] = stats["by_type"].get(t, 0) + 1
    stats["cases"][p["case_id"]] = stats["cases"].get(p["case_id"], 0) + 1

print("Stats:", json.dumps(stats, indent=2))
(OUT / "dpo_stats.json").write_text(json.dumps(stats, indent=2))
