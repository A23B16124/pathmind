"""
Retry degraded rejected runs: remove entries missing synoptic/diagnosis_line,
then re-run them with old prompts (breast-biased) via phase1.
"""
from __future__ import annotations
import json, sys, time, shutil, requests
from pathlib import Path

API = "http://localhost:8011"
OUT_FILE = Path("/root/pathmind/data/training_raw/rejected_runs.jsonl")
MANIFEST = Path("/root/pathmind/data/benchmark/manifest.json")
PROMPT_DIR = Path("/root/pathmind/backend/prompts")
OLD_PROMPTS = {
    "02_histopathologist.txt": Path("/tmp/old_02_histopathologist.txt"),
    "03_cross_slide_aggregator.txt": Path("/tmp/old_03_cross_slide_aggregator.txt"),
    "04_literature_hunter.txt": Path("/tmp/old_04_literature_hunter.txt"),
    "05_differential_diagnostician.txt": Path("/tmp/old_05_differential_diagnostician.txt"),
    "07_report_writer.txt": Path("/tmp/old_07_report_writer.txt"),
}
SLIDE_DIR = "tcga"
POLL_INTERVAL = 15
MAX_WAIT = 900

# --- helpers ----------------------------------------------------------------

def is_degraded(r: dict) -> bool:
    if r.get("error"):
        return True
    report = r.get("report", {})
    cap = report.get("report", report) if isinstance(report.get("report"), dict) else report
    return not (cap.get("synoptic") and cap.get("diagnosis_line"))

def swap_prompts(version: str):
    backup_dir = Path("/tmp/prompt_backup_new")
    if version == "old":
        backup_dir.mkdir(exist_ok=True)
        for fname, old_path in OLD_PROMPTS.items():
            target = PROMPT_DIR / fname
            shutil.copy2(target, backup_dir / fname)
            shutil.copy2(old_path, target)
        print("[prompts] Swapped to OLD (breast-biased)")
    else:
        for fname in OLD_PROMPTS:
            target = PROMPT_DIR / fname
            src = backup_dir / fname
            if src.exists():
                shutil.copy2(src, target)
        print("[prompts] Restored to NEW (corrected)")
    time.sleep(8)
    for _ in range(20):
        try:
            r = requests.get(f"{API}/health", timeout=5)
            if r.status_code < 400:
                print("[api] Backend ready")
                return
        except Exception:
            pass
        time.sleep(3)
    raise RuntimeError("Backend did not come back up")

def start_case(sub: str, slides: list[str], prefix: str = "rej") -> str:
    paths = [f"{SLIDE_DIR}/{s}" for s in slides]
    payload = {"case_id": f"{prefix}-{sub}", "patient_id": sub, "slide_paths": paths}
    r = requests.post(f"{API}/api/analyze", json=payload, timeout=30)
    r.raise_for_status()
    return r.json()["case_id"]

def poll_case(case_id: str) -> dict:
    deadline = time.time() + MAX_WAIT
    while time.time() < deadline:
        try:
            q = requests.get(f"{API}/api/queue", timeout=10).json()
            active = {c["case_id"] for c in q.get("active_cases", [])}
            r = requests.get(f"{API}/api/case/{case_id}/report", timeout=10)
            if r.status_code == 200:
                d = r.json()
                if d.get("report") or case_id not in active:
                    return d
        except Exception as e:
            print(f"    poll error: {e}")
        time.sleep(POLL_INTERVAL)
    raise RuntimeError(f"Timeout waiting for {case_id}")

# --- main -------------------------------------------------------------------

def main():
    # 1. Load existing runs, split clean vs degraded
    lines = [l for l in OUT_FILE.read_text().splitlines() if l.strip()]
    records = []
    for l in lines:
        try:
            records.append(json.loads(l))
        except:
            pass

    clean = [r for r in records if not is_degraded(r)]
    degraded_ids = {r["submitter_id"] for r in records if is_degraded(r)}
    print(f"Clean: {len(clean)}  |  Degraded: {len(degraded_ids)}")

    if not degraded_ids:
        print("Nothing to retry.")
        return

    # 2. Load manifest to get slides for degraded cases
    manifest = json.loads(MANIFEST.read_text())
    if isinstance(manifest, dict) and "cases" in manifest:
        manifest = manifest["cases"]

    # Map submitter_id -> case
    case_map = {c["submitter_id"]: c for c in manifest}

    # 3. Truncate file to only clean runs
    with open(OUT_FILE, "w", encoding="utf-8") as fh:
        for r in clean:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"Truncated {OUT_FILE.name} to {len(clean)} clean entries")

    # 4. Swap to old prompts
    swap_prompts("old")

    # 5. Run degraded cases in batches of 3
    to_run = [case_map[sid] for sid in degraded_ids if sid in case_map]
    missing = [sid for sid in degraded_ids if sid not in case_map]
    if missing:
        print(f"WARNING: {len(missing)} degraded cases not in manifest: {missing}")

    print(f"\nRetrying {len(to_run)} cases...")
    batch_size = 3
    succeeded = 0
    failed = 0

    with open(OUT_FILE, "a", encoding="utf-8") as fh:
        i = 0
        while i < len(to_run):
            batch = to_run[i:i+batch_size]
            launched = []
            for case in batch:
                sub = case["submitter_id"]
                slides = [s["file_name"] for s in case.get("slides", [])]
                try:
                    cid = start_case(sub, slides, "rej")
                    launched.append((sub, cid, case))
                    print(f"  Started {sub} -> {cid}")
                except Exception as e:
                    print(f"  FAILED to start {sub}: {e}")
                    failed += 1

            for sub, cid, case in launched:
                try:
                    report = poll_case(cid)
                    record = {"submitter_id": sub, "case_id": cid, "report": report, "gt": case.get("gt")}
                    fh.write(json.dumps(record, ensure_ascii=False) + "\n")
                    fh.flush()
                    cap = report.get("report", report) if isinstance(report.get("report"), dict) else report
                    ok = bool(cap.get("synoptic") and cap.get("diagnosis_line"))
                    print(f"  Done {sub}: {'OK' if ok else 'DEGRADED AGAIN'}")
                    succeeded += 1
                except Exception as e:
                    err = {"submitter_id": sub, "case_id": cid, "error": str(e), "gt": case.get("gt")}
                    fh.write(json.dumps(err, ensure_ascii=False) + "\n")
                    fh.flush()
                    print(f"  ERROR {sub}: {e}")
                    failed += 1

            i += batch_size

    print(f"\nRetry done. Succeeded: {succeeded}  |  Failed: {failed}")
    print(f"Total in {OUT_FILE.name}: {len(clean) + succeeded} entries")

    # 6. Restore new prompts
    swap_prompts("new")

if __name__ == "__main__":
    main()
