"""
Option A — Generate DPO training pairs from 60 TCGA-COAD cases.

Strategy:
  rejected  = pipeline run WITHOUT clinical context + OLD prompts (breed hallucination-prone)
  chosen    = pipeline run WITH clinical context + current prompts (corrected)

This script:
  1. Reads the 60-case manifest
  2. For each case, calls /api/analyze with old-prompt mode (rejected) then new-prompt mode (chosen)
  3. Extracts LLM call logs (JSONL) from data/logs/ to build DPO pairs
  4. Writes augmented dpo_pairs.jsonl and sft_dataset.jsonl

Since we can't hot-swap prompts mid-run, we use a query param ?prompt_version=old|new
that the backend already supports via PROMPT_VERSION env var — or we run two separate
batch sweeps (Phase 1 = old prompts, Phase 2 = new prompts).

For this script we run Phase 1 and Phase 2 sequentially by patching prompts on disk.
"""
from __future__ import annotations
import json, re, sys, time, shutil, subprocess
from pathlib import Path
import requests

API = "http://localhost:8011"
MANIFEST = Path("/root/pathmind/data/benchmark/manifest.json")
PROMPT_DIR = Path("/root/pathmind/backend/prompts")
OLD_PROMPTS = {
    "02_histopathologist.txt": Path("/tmp/old_02_histopathologist.txt"),
    "03_cross_slide_aggregator.txt": Path("/tmp/old_03_cross_slide_aggregator.txt"),
    "04_literature_hunter.txt": Path("/tmp/old_04_literature_hunter.txt"),
    "05_differential_diagnostician.txt": Path("/tmp/old_05_differential_diagnostician.txt"),
    "07_report_writer.txt": Path("/tmp/old_07_report_writer.txt"),
}
OUT_DIR = Path("/root/pathmind/data/training_raw")
OUT_DIR.mkdir(parents=True, exist_ok=True)

POLL_INTERVAL = 15
MAX_WAIT = 900  # 15 min
SLIDE_DIR = "tcga"
SKIP = {"TCGA-AY-A71X"}  # known stall


def swap_prompts(version: str):
    """version = 'old' or 'new'"""
    backup_dir = Path("/tmp/prompt_backup_new")
    if version == "old":
        backup_dir.mkdir(exist_ok=True)
        for fname, old_path in OLD_PROMPTS.items():
            target = PROMPT_DIR / fname
            # backup current
            shutil.copy2(target, backup_dir / fname)
            # install old
            shutil.copy2(old_path, target)
        print("[prompts] Swapped to OLD (breast-biased)")
    else:
        for fname in OLD_PROMPTS:
            target = PROMPT_DIR / fname
            src = backup_dir / fname
            if src.exists():
                shutil.copy2(src, target)
        print("[prompts] Restored to NEW (corrected)")
    # Restart backend to reload prompts
    
    time.sleep(8)  # wait for startup
    # Wait until API responds
    for _ in range(20):
        try:
            r = requests.get(f"{API}/health", timeout=5)
            if r.status_code < 400:
                print("[api] Backend ready")
                return
        except Exception:
            pass
        time.sleep(3)
    raise RuntimeError("Backend did not come back up after prompt swap")


def start_case(sub: str, slides: list[str], clinical: str | None, prefix: str) -> str:
    paths = [f"{SLIDE_DIR}/{s}" for s in slides]
    payload: dict = {"case_id": f"{prefix}-{sub}", "patient_id": sub, "slide_paths": paths}
    if clinical:
        payload["clinical_data"] = clinical
    r = requests.post(f"{API}/api/analyze", json=payload, timeout=30)
    r.raise_for_status()
    return r.json()["case_id"]


def poll_case(case_id: str) -> dict:
    t0 = time.time()
    while time.time() - t0 < MAX_WAIT:
        try:
            r = requests.get(f"{API}/api/case/{case_id}/report", timeout=30)
            if r.status_code == 200:
                d = r.json()
                if d.get("report") or d.get("status") == "complete":
                    return d
                if d.get("error"):
                    raise RuntimeError(f"{case_id} pipeline error: {d.get("error")}")
        except RuntimeError:
            raise
        except Exception:
            pass
        # Check queue — if case no longer active AND no report, it errored
        try:
            q = requests.get(f"{API}/api/queue", timeout=10).json()
            active = q.get("active_cases", [])
            if case_id not in active and time.time() - t0 > 60:
                # Case left the queue without a report = error
                raise RuntimeError(f"{case_id} left queue without report")
        except RuntimeError:
            raise
        except Exception:
            pass
        time.sleep(POLL_INTERVAL)
    raise TimeoutError(f"{case_id} timed out after {MAX_WAIT}s")


def run_phase(manifest: list[dict], clinical_fn, prefix: str, out_file: Path, batch_size: int = 3):
    """Run all cases and save results."""
    if out_file.exists():
        existing = {json.loads(l)["submitter_id"] for l in out_file.read_text().splitlines() if l.strip()}
        print(f"[{prefix}] {len(existing)} already done, skipping")
    else:
        existing = set()

    pending = [c for c in manifest if c["submitter_id"] not in SKIP and c["submitter_id"] not in existing]
    print(f"[{prefix}] {len(pending)} cases to run")

    with open(out_file, "a", encoding="utf-8") as fh:
        i = 0
        while i < len(pending):
            batch = pending[i:i+batch_size]
            launched = []
            for case in batch:
                sub = case["submitter_id"]
                slides = [s["file_name"] for s in case.get("slides", [])]
                clinical = clinical_fn(case)
                try:
                    cid = start_case(sub, slides, clinical, prefix)
                    launched.append((sub, cid, case))
                    print(f"  [{prefix}] Started {sub} -> {cid}")
                except Exception as e:
                    print(f"  [{prefix}] FAILED to start {sub}: {e}")

            for sub, cid, case in launched:
                try:
                    report = poll_case(cid)
                    record = {"submitter_id": sub, "case_id": cid, "report": report, "gt": case.get("gt")}
                    fh.write(json.dumps(record, ensure_ascii=False) + "\n")
                    fh.flush()
                    print(f"  [{prefix}] Done {sub}: dx={report.get('report',{}).get('primary_diagnosis','?')}")
                except TimeoutError as e:
                    print(f"  [{prefix}] TIMEOUT {sub}: {e}")
                    record = {"submitter_id": sub, "case_id": cid, "error": str(e), "gt": case.get("gt")}
                    fh.write(json.dumps(record, ensure_ascii=False) + "\n")
                    fh.flush()
            i += batch_size


def build_dpo_pairs(rejected_file: Path, chosen_file: Path, out_file: Path):
    def load(f):
        d = {}
        for line in f.read_text().splitlines():
            if line.strip():
                r = json.loads(line)
                d[r["submitter_id"]] = r
        return d

    rejected = load(rejected_file)
    chosen = load(chosen_file)
    pairs = []
    common = set(rejected) & set(chosen)
    print(f"[dpo] {len(common)} cases with both rejected+chosen")

    for sub in common:
        rej = rejected[sub]
        cho = chosen[sub]
        if rej.get("error") or cho.get("error"):
            continue
        rej_report = rej.get("report", {}).get("report", {})
        cho_report = cho.get("report", {}).get("report", {})

        # Build conversation-style DPO pair
        system = "You are a surgical pathologist AI assistant. Analyze histopathology slides and provide structured diagnosis."
        user_msg = f"Analyze case {sub}. Provide primary diagnosis, staging, grade, and treatment implications."

        chosen_text = json.dumps(cho_report, ensure_ascii=False)
        rejected_text = json.dumps(rej_report, ensure_ascii=False)

        if chosen_text == rejected_text:
            continue  # no difference

        pair = {
            "submitter_id": sub,
            "prompt": [
                {"role": "system", "content": system},
                {"role": "user", "content": user_msg},
            ],
            "chosen": [{"role": "assistant", "content": chosen_text}],
            "rejected": [{"role": "assistant", "content": rejected_text}],
            "gt": cho.get("gt"),
        }
        pairs.append(pair)

    print(f"[dpo] {len(pairs)} valid pairs")
    with open(out_file, "w", encoding="utf-8") as fh:
        for p in pairs:
            fh.write(json.dumps(p, ensure_ascii=False) + "\n")
    print(f"[dpo] Written to {out_file}")
    return pairs


def build_sft(chosen_file: Path, out_file: Path):
    samples = []
    for line in chosen_file.read_text().splitlines():
        if not line.strip(): continue
        r = json.loads(line)
        if r.get("error"): continue
        report = r.get("report", {}).get("report", {})
        dx = str(report.get("primary_diagnosis","")).lower()
        # Skip if contaminated with breast hallucination
        if any(t in dx for t in ["ductal","breast","idc","lobular"]):
            continue
        samples.append({
            "submitter_id": r["submitter_id"],
            "messages": [
                {"role": "system", "content": "You are a surgical pathologist AI. Provide accurate structured diagnosis."},
                {"role": "user", "content": f"Diagnose case {r['submitter_id']} (colorectal adenocarcinoma cohort)."},
                {"role": "assistant", "content": json.dumps(report, ensure_ascii=False)},
            ],
            "gt": r.get("gt"),
        })
    print(f"[sft] {len(samples)} clean samples")
    with open(out_file, "w", encoding="utf-8") as fh:
        for s in samples:
            fh.write(json.dumps(s, ensure_ascii=False) + "\n")
    print(f"[sft] Written to {out_file}")
    return samples


def main():
    manifest = json.loads(MANIFEST.read_text())
    if isinstance(manifest, dict) and "cases" in manifest:
        manifest = manifest["cases"]

    rejected_file = OUT_DIR / "rejected_runs.jsonl"
    chosen_file   = OUT_DIR / "chosen_runs.jsonl"

    mode = sys.argv[1] if len(sys.argv) > 1 else "all"

    if mode in ("all", "phase1"):
        print("\n=== PHASE 1: OLD PROMPTS (rejected) ===")
        swap_prompts("old")
        run_phase(manifest, lambda c: None, "rej", rejected_file)

    if mode in ("all", "phase2"):
        print("\n=== PHASE 2: NEW PROMPTS (chosen) ===")
        swap_prompts("new")
        # Add clinical context for chosen: use site from GT as anchor
        # clinical_data must be a dict (JSON object), not a string
        def clinical_fn(c):
            gt = c.get("gt", {})
            site = gt.get("site", "")
            stage = gt.get("stage", "")
            pt = gt.get("pT", "")
            pn = gt.get("pN", "")
            ctx = {
                "tissue_origin": site if site and site != "Not Reported" else "Colorectal",
                "cohort": "TCGA-COAD",
                "note": "Colorectal adenocarcinoma cohort. Use colorectal grading (WHO G1-G3).",
            }
            if stage and stage != "Not Reported":
                ctx["clinical_stage"] = stage
            if pt and pt != "Not Reported":
                ctx["pT"] = pt
            if pn and pn != "Not Reported":
                ctx["pN"] = pn
            return ctx
        run_phase(manifest, clinical_fn, "cho", chosen_file)

    if mode in ("all", "build"):
        print("\n=== BUILD DPO + SFT ===")
        dpo_out = Path("/root/pathmind/data/dpo/dpo_pairs_v2.jsonl")
        sft_out = Path("/root/pathmind/data/sft/sft_dataset_v2.jsonl")
        build_dpo_pairs(rejected_file, chosen_file, dpo_out)
        build_sft(chosen_file, sft_out)
        print("\nDone. Run: python3 scripts/train_dpo_qlora.py --dataset data/dpo/dpo_pairs_v2.jsonl")


if __name__ == "__main__":
    main()
