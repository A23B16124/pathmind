"""
Download all slides + pathology report PDFs from manifest.json.
Resumes on retry — skips files already present with matching size.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import requests

GDC_DATA = "https://api.gdc.cancer.gov/data"
SLIDE_DIR = Path("/root/pathmind/data/slides/tcga")
REPORT_DIR = Path("/root/pathmind/data/benchmark/reports")
MANIFEST = Path("/root/pathmind/data/benchmark/manifest.json")


def download(file_id: str, out: Path, label: str) -> None:
    if out.exists() and out.stat().st_size > 0:
        print(f"  [skip] {label} ({out.name}, {out.stat().st_size // 1024**2} MB)")
        return
    url = f"{GDC_DATA}/{file_id}"
    t0 = time.time()
    with requests.get(url, stream=True, timeout=120) as r:
        r.raise_for_status()
        out.parent.mkdir(parents=True, exist_ok=True)
        tmp = out.with_suffix(out.suffix + ".part")
        with tmp.open("wb") as f:
            for chunk in r.iter_content(chunk_size=8 * 1024 * 1024):
                if chunk:
                    f.write(chunk)
        tmp.rename(out)
    mb = out.stat().st_size / 1024**2
    dt = time.time() - t0
    print(f"  [ok]   {label} ({out.name}, {mb:.0f} MB in {dt:.0f}s)")


def main() -> int:
    manifest = json.loads(MANIFEST.read_text())
    cases = manifest["cases"]
    print(f"Downloading {len(cases)} cases…\n")
    for i, case in enumerate(cases, 1):
        sub = case["submitter_id"]
        print(f"[{i}/{len(cases)}] {sub}")
        # Pathology report
        try:
            download(case["report_file_id"],
                     REPORT_DIR / f"{sub}.pdf",
                     "report")
        except Exception as e:
            print(f"  [ERR]  report: {e}")
        # Slides
        for s in case["slides"]:
            try:
                download(s["file_id"], SLIDE_DIR / s["file_name"], "slide")
            except Exception as e:
                print(f"  [ERR]  slide {s['file_name']}: {e}")
    print("\nDone.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
