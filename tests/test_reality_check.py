import subprocess
import json
import sys
from pathlib import Path


def test_reality_check_runs(tmp_path):
    (tmp_path / "src").mkdir()
    # Create a real implementation file (>100 bytes)
    (tmp_path / "src" / "dummy.py").write_text(
        "def hello():\n    return 'hello world'\n\n"
        "def goodbye():\n    return 'goodbye'\n\n"
        "def add(a, b):\n    return a + b\n"
    )
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_dummy.py").write_text("def test_ok():\n    assert 1 == 1\n")

    result = subprocess.run(
        [sys.executable, "scripts/reality_check.py", "--path", str(tmp_path), "--dry-run"],
        capture_output=True, text=True, timeout=30,
        cwd="/home/ubuntu/pathmind"
    )
    assert result.returncode == 0, f"stderr: {result.stderr}\nstdout: {result.stdout}"
    output = json.loads(result.stdout)
    assert output["verdict"] in ("on_track", "at_risk", "hallucinating")
    assert "demo_ready_pct" in output
    assert "implemented_files" in output
