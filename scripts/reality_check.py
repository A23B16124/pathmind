#!/usr/bin/env python3
"""
Reality Check Agent — subprocess isolé, zéro mémoire partagée hackathon.
Usage : python scripts/reality_check.py --path /opt/pathmind/workspace [--dry-run]
Output : JSON sur stdout avec verdict on_track / at_risk / hallucinating
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path


def count_stubs(path: Path) -> list[str]:
    src_dir = path / "src"
    if not src_dir.exists():
        return []
    result = subprocess.run(
        ["grep", "-rn", "--include=*.py", r"pass$\|raise NotImplementedError\|# TODO", str(src_dir)],
        capture_output=True, text=True
    )
    return [l.strip() for l in result.stdout.splitlines() if l.strip()]


def count_tests(path: Path) -> int:
    tests_dir = path / "tests"
    if not tests_dir.exists():
        return 0
    result = subprocess.run(
        ["grep", "-rn", "--include=*.py", r"^def test_", str(tests_dir)],
        capture_output=True, text=True
    )
    return len(result.stdout.splitlines())


def run_tests(path: Path) -> tuple[bool, str]:
    result = subprocess.run(
        ["python3", "-m", "pytest", str(path / "tests"), "-x", "-q", "--tb=no"],
        capture_output=True, text=True, timeout=120, cwd=str(path)
    )
    return result.returncode == 0, (result.stdout + result.stderr)[-500:]


def count_implemented_files(path: Path) -> list[str]:
    src = path / "src"
    if not src.exists():
        return []
    return [str(f.relative_to(path)) for f in src.rglob("*.py") if f.stat().st_size > 100]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--path", default=".")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    workspace = Path(args.path).resolve()
    stubs = count_stubs(workspace)
    n_tests = count_tests(workspace)
    implemented = count_implemented_files(workspace)

    if args.dry_run:
        tests_pass, test_output = True, "dry-run"
    else:
        tests_pass, test_output = run_tests(workspace)

    n_stubs = len(stubs)
    n_impl = len(implemented)

    if n_impl == 0:
        verdict = "hallucinating"
    elif n_stubs > 10 or n_tests == 0 or (not tests_pass and not args.dry_run):
        verdict = "at_risk"
    else:
        verdict = "on_track"

    demo_pct = min(100, max(0, int((n_impl / max(n_impl + n_stubs, 1)) * 100)))

    print(json.dumps({
        "verdict": verdict,
        "implemented_files": implemented,
        "stub_lines": stubs[:10],
        "test_count": n_tests,
        "tests_pass": tests_pass,
        "demo_ready_pct": demo_pct,
        "blockers": stubs[:5] if verdict != "on_track" else [],
        "recommendation": (
            "Tout semble en ordre." if verdict == "on_track"
            else "Stubs ou tests manquants — vérifiez les fichiers listés." if verdict == "at_risk"
            else "Aucun fichier source implémenté — commencez par le Task 1."
        ),
        "test_output_tail": test_output,
    }, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
