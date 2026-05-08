"""
Build final DPO + SFT datasets from phase1 (rejected) and phase2 (chosen) runs.
"""
import json, sys
from pathlib import Path

REJ_FILE  = Path("/root/pathmind/data/training_raw/rejected_runs.jsonl")
CHO_FILE  = Path("/root/pathmind/data/training_raw/chosen_runs.jsonl")
DPO_OUT   = Path("/root/pathmind/data/dpo/dpo_pairs_v2.jsonl")
SFT_OUT   = Path("/root/pathmind/data/sft/sft_dataset_v2.jsonl")
STATS_OUT = Path("/root/pathmind/data/training_raw/build_stats.json")

SYSTEM = (
    "You are an expert surgical pathologist AI assistant embedded in the PathMind "
    "multi-agent diagnostic system. Analyze histopathology slides and produce structured "
    "diagnoses following WHO classification guidelines. For colorectal specimens, use "
    "WHO G1-G3 grading. Never assume breast/ductal origin without explicit clinical context."
)

BREAST_TERMS = {"ductal", "idc", "breast", "invasive ductal", "idc-nst", "lobular", "sbr"}


def load_runs(path):
    runs = {}
    for line in path.read_text().splitlines():
        if not line.strip(): continue
        r = json.loads(line)
        runs[r["submitter_id"]] = r
    return runs


def extract_report(run):
    rep = run.get("report", {})
    if isinstance(rep, dict):
        inner = rep.get("report")
        if isinstance(inner, dict) and inner:
            return inner
        return rep
    return {}


def has_breast(report):
    fields = [str(report.get(k,"")) for k in ["diagnosis","primary_diagnosis","diagnosis_line"]]
    cap = report.get("cap_report") or {}
    fields.append(str(cap.get("diagnosis_line","")))
    combined = " ".join(fields).lower()
    return any(t in combined for t in BREAST_TERMS)


def is_correct_crc(report):
    fields = [str(report.get(k,"")) for k in ["diagnosis","primary_diagnosis","diagnosis_line"]]
    combined = " ".join(fields).lower()
    crc = {"adenocarcinoma","colorectal","colon","rectal","crc"}
    return any(t in combined for t in crc) and not has_breast(report)


def user_prompt(sub, gt):
    site = (gt or {}).get("site","colorectal")
    if not site or site == "Not Reported": site = "colorectal"
    return (f"Analyze histopathology slides for case {sub}. Tissue origin: {site}. "
            f"TCGA-COAD colorectal adenocarcinoma cohort. Provide structured diagnosis "
            f"with primary diagnosis, staging, grade, biomarkers, and treatment implications.")


def main():
    rejected = load_runs(REJ_FILE)
    print(f"Rejected: {len(rejected)}")
    if not CHO_FILE.exists():
        print("chosen_runs.jsonl missing — phase2 incomplete"); sys.exit(1)
    chosen = load_runs(CHO_FILE)
    print(f"Chosen: {len(chosen)}")

    common = set(rejected) & set(chosen)
    dpo, sft = [], []
    stats = dict(total=len(common), dpo=0, sft=0, breast_rej=0, correct_cho=0, no_diff=0)

    for sub in sorted(common):
        rr, cr = rejected[sub], chosen[sub]
        if rr.get("error") or cr.get("error"): continue
        rr_rep, cr_rep = extract_report(rr), extract_report(cr)
        if not rr_rep or not cr_rep: continue

        r_breast = has_breast(rr_rep)
        c_crc    = is_correct_crc(cr_rep)
        if r_breast: stats["breast_rej"] += 1
        if c_crc:    stats["correct_cho"] += 1

        ct = json.dumps(cr_rep, ensure_ascii=False)
        rt = json.dumps(rr_rep, ensure_ascii=False)
        if ct == rt: stats["no_diff"] += 1; continue

        gt = cr.get("gt") or rr.get("gt")
        um = user_prompt(sub, gt)
        dpo.append({"submitter_id": sub,
                    "prompt":   [{"role":"system","content":SYSTEM},{"role":"user","content":um}],
                    "chosen":   [{"role":"assistant","content":ct}],
                    "rejected": [{"role":"assistant","content":rt}],
                    "meta":     {"rej_breast":r_breast,"cho_crc":c_crc,
                                 "gt_dx":(gt or {}).get("primary_diagnosis",""),
                                 "gt_site":(gt or {}).get("site","")}})
        if c_crc:
            sft.append({"submitter_id": sub,
                        "messages":[{"role":"system","content":SYSTEM},
                                    {"role":"user","content":um},
                                    {"role":"assistant","content":ct}],
                        "gt":gt})

    stats["dpo"], stats["sft"] = len(dpo), len(sft)
    DPO_OUT.parent.mkdir(parents=True, exist_ok=True)
    SFT_OUT.parent.mkdir(parents=True, exist_ok=True)
    DPO_OUT.write_text("\n".join(json.dumps(p,ensure_ascii=False) for p in dpo)+"\n")
    SFT_OUT.write_text("\n".join(json.dumps(s,ensure_ascii=False) for s in sft)+"\n")
    STATS_OUT.write_text(json.dumps(stats,indent=2))

    print(f"\n=== BUILD COMPLETE ===")
    print(f"DPO pairs:  {stats['dpo']} -> {DPO_OUT}")
    print(f"SFT samples:{stats['sft']} -> {SFT_OUT}")
    print(f"Breast hallucinations in rejected: {stats['breast_rej']}/{len(common)}")
    print(f"Correct CRC in chosen:             {stats['correct_cho']}/{len(common)}")
    print(f"Skipped (no diff):                 {stats['no_diff']}")

if __name__ == "__main__":
    main()
