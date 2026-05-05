"""
On-disk cache of completed pipeline reports.

Avoids re-running the 5–10-minute LangGraph dual-read pipeline for cases
the demo will replay (Dubois, TCGA-OL-A66K, TCGA-2L-AAQJ). Cache key is
the case_id; payload is the full `report_dict` plus the timestamped
event stream produced during the live run.

Cache lives under `data/demo_reports/` (gitignored except for committed
seeds). One JSON file per case_id.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Optional

CACHE_DIR = Path(__file__).resolve().parents[2] / "data" / "demo_reports"


def _path(case_id: str) -> Path:
    safe = "".join(c if c.isalnum() or c in "-_." else "_" for c in case_id)[:120]
    return CACHE_DIR / f"{safe}.json"


def load(case_id: str) -> Optional[dict]:
    """Return the cached payload, or None if absent / unreadable."""
    p = _path(case_id)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def save(case_id: str, report_dict: dict, events: Optional[list] = None) -> Path:
    """Persist the report. `events` is the optional broadcast trace for replay."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "case_id": case_id,
        "saved_at": int(time.time()),
        "report": report_dict,
        "events": events or [],
    }
    p = _path(case_id)
    p.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return p
