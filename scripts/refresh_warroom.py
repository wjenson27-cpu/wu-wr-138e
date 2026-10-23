#!/usr/bin/env python3
"""Single War Room refresh runner. Stages a copy of data/, runs the refreshers on the copy, validates every JSON
file, runs the tests, and only then copies changed files back into data/. Any failure exits nonzero and leaves
data/ untouched. It never commits or pushes; the calling routine reviews and pushes as before (merge to main is Bill's).

  --mode full  (box routines): free agents + warroom (Fantrax files on the box) + green dots
  --mode ci    (GitHub Actions): green dots + JSON validation only (no box browser / Fantrax files)
"""
import argparse, json, os, shutil, subprocess, sys, tempfile
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
PY = sys.executable

def sh(cmd, **kw):
    print("+", " ".join(map(str, cmd)), flush=True)
    r = subprocess.run(cmd, capture_output=True, text=True, **kw)
    sys.stdout.write(r.stdout); sys.stderr.write(r.stderr)
    return r

def known_failing():
    f = ROOT / "tests" / "KNOWN_FAILING.txt"
    return {l.strip() for l in f.read_text().splitlines() if l.strip() and not l.startswith("#")} if f.exists() else set()

def run_tests(stage):
    env = dict(os.environ, WU_DATA_DIR=str(stage))
    r = sh([PY, "-m", "unittest", "discover", "-s", str(ROOT / "tests" / "py")], cwd=ROOT, env=env)
    if r.returncode:
        return "python tests failed"
    if shutil.which("node"):
        r = sh(["node", "--test", "tests/"], cwd=ROOT)
        bad = {l.split(" - ", 1)[1].strip() for l in r.stdout.splitlines() if l.startswith("not ok") and " - " in l}
        new = bad - known_failing()
        if new:
            return f"node tests failed (not in tests/KNOWN_FAILING.txt): {sorted(new)}"
    return None

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["full", "ci"], default="full")
    ap.add_argument("--dry-run", action="store_true", help="stage + check, do not copy back")
    ap.add_argument("--skip-tests", action="store_true")
    a = ap.parse_args()
    data = ROOT / "data"
    with tempfile.TemporaryDirectory(prefix="wr-stage-") as t:
        stage = Path(t) / "data"
        shutil.copytree(data, stage)
        steps = [[PY, ROOT / "scripts/refresh_green_dots.py", "--data-dir", stage]]
        if a.mode == "full":
            steps = [[PY, ROOT / "scripts/build_free_agents.py", "--data-dir", stage],
                     [PY, ROOT / "scripts/build_warroom.py", "--data-dir", stage]] + steps
        for c in steps:
            if sh(list(map(str, c))).returncode:
                print("FAIL step:", c[1]); return 1
        errs = []
        for f in stage.rglob("*.json"):
            try: json.loads(f.read_text())
            except Exception as e: errs.append(f"{f.relative_to(stage)}: {e}")
        if errs:
            print("FAIL json:", errs); return 1
        if not a.skip_tests:
            e = run_tests(stage)
            if e:
                print("FAIL tests:", e); return 1
        changed = [f.relative_to(stage) for f in stage.rglob("*") if f.is_file()
                   and (not (data / f.relative_to(stage)).exists() or (data / f.relative_to(stage)).read_bytes() != f.read_bytes())]
        print("changed:", [str(c) for c in changed])
        if a.dry_run:
            print("dry run: data/ untouched"); return 0
        for c in changed:
            (data / c).parent.mkdir(parents=True, exist_ok=True)
            tmp = data / (str(c) + ".tmp"); shutil.copyfile(stage / c, tmp); os.replace(tmp, data / c)
        print("OK"); return 0

if __name__ == "__main__":
    sys.exit(main())
