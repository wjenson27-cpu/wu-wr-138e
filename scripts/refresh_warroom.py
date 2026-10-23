#!/usr/bin/env python3
"""Single War Room refresh runner (fail closed, all-or-nothing).

1. Copies the whole repo (minus .git) to a temp stage dir.
2. Runs the refreshers on stage/data.
3. Validates every JSON file in stage/data, runs the deny-pending gate on warroom.json + free-agents.json,
   and runs the Python and node tests INSIDE the stage (so they test the data about to be published).
4. Only if all of that passes, swaps stage/data in for data/ with renames on the same filesystem; on any
   error during the swap it renames the original back. No .tmp files are left behind.
It never commits or pushes. Merge to main is Bill's.

  --mode full  (box routines): free agents + warroom (Fantrax files on the box) + green dots
  --mode ci    (GitHub Actions): green dots + JSON validation + tests (no box browser / Fantrax files)
"""
import argparse, json, os, re, shutil, subprocess, sys, tempfile
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
PY = sys.executable
sys.path.insert(0, str(ROOT / "scripts"))
from warroom_common import find_pending

class Fail(Exception): pass

def sh(cmd, **kw):
    print("+", " ".join(map(str, cmd)), flush=True)
    r = subprocess.run(list(map(str, cmd)), capture_output=True, text=True, **kw)
    sys.stdout.write(r.stdout); sys.stderr.write(r.stderr)
    return r

def known_failing(root):
    f = root / "tests" / "KNOWN_FAILING.txt"
    return {l.strip() for l in f.read_text().splitlines() if l.strip() and not l.startswith("#")} if f.exists() else set()

NOT_OK = re.compile(r"^\s*not ok \d+ - (.*?)\s*(#.*)?$")
def node_verdict(rc, out, allowed):
    """Return None if OK, else a reason. Nested (indented) failures count. A crash (nonzero exit with no
    recognised failure lines, or no TAP summary) is a failure."""
    bad = [m.group(1) for m in map(NOT_OK.match, out.splitlines()) if m]
    if rc != 0 and not bad:
        return f"node exited {rc} with no failing test lines (crash?)"
    if not re.search(r"^# pass \d+", out, re.M):
        return "node produced no TAP summary (crash?)"
    new = sorted(set(bad) - allowed)
    return f"node tests failed (not in tests/KNOWN_FAILING.txt): {new}" if new else None

def run_tests(stage_root):
    env = dict(os.environ, WU_DATA_DIR=str(stage_root / "data"))
    r = sh([PY, "-m", "unittest", "discover", "-s", stage_root / "tests" / "py"], cwd=stage_root, env=env)
    if r.returncode:
        raise Fail("python tests failed")
    if not shutil.which("node"):
        raise Fail("node not found (tests cannot run)")
    r = sh(["node", "--test", "tests/"], cwd=stage_root)
    v = node_verdict(r.returncode, r.stdout + r.stderr, known_failing(stage_root))
    if v:
        raise Fail(v)

def validate(stage_data):
    errs = []
    for f in stage_data.rglob("*.json"):
        try:
            json.loads(f.read_text())
        except Exception as e:
            errs.append(f"{f.relative_to(stage_data)}: {e}")
    if errs:
        raise Fail(f"invalid JSON: {errs}")
    for name in ("warroom.json", "free-agents.json"):
        p = stage_data / name
        if p.exists():
            h = find_pending(json.loads(p.read_text()))
            if h:
                raise Fail(f"pending item(s) in {name}: {h[:10]}")

def changed_files(stage_data, data):
    out = []
    for f in stage_data.rglob("*"):
        if f.is_file():
            rel = f.relative_to(stage_data); d = data / rel
            if not d.exists() or d.read_bytes() != f.read_bytes():
                out.append(str(rel))
    return sorted(out)

def swap_in(stage_data, data, _rename=os.rename):
    """All-or-nothing: copy stage data next to data/ (same filesystem), then two renames.
    If the second rename fails, the first is undone."""
    new = Path(tempfile.mkdtemp(prefix=".data-new-", dir=data.parent))
    old = data.parent / (".data-old-" + new.name.split("-")[-1])
    try:
        shutil.rmtree(new); shutil.copytree(stage_data, new)
        _rename(data, old)
        try:
            _rename(new, data)
        except BaseException:
            _rename(old, data)
            raise
    finally:
        if new.exists(): shutil.rmtree(new, ignore_errors=True)
    shutil.rmtree(old, ignore_errors=True)

def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["full", "ci"], default="full")
    ap.add_argument("--dry-run", action="store_true", help="stage + check, do not copy back")
    ap.add_argument("--skip-tests", action="store_true")
    ap.add_argument("--root", default=str(ROOT))
    a = ap.parse_args(argv)
    root = Path(a.root).resolve(); data = root / "data"
    with tempfile.TemporaryDirectory(prefix="wr-stage-") as t:
        stage = Path(t) / "repo"
        shutil.copytree(root, stage, ignore=shutil.ignore_patterns(".git", "node_modules", "__pycache__", ".data-*"))
        sd = stage / "data"
        try:
            steps = [[PY, stage / "scripts/refresh_green_dots.py", "--data-dir", sd]]
            if a.mode == "full":
                steps = [[PY, stage / "scripts/build_free_agents.py", "--data-dir", sd],
                         [PY, stage / "scripts/build_warroom.py", "--data-dir", sd]] + steps
            for c in steps:
                if sh(c).returncode:
                    raise Fail(f"step failed: {Path(str(c[1])).name}")
            validate(sd)
            if not a.skip_tests:
                run_tests(stage)
            ch = changed_files(sd, data)
            print("changed:", ch)
            if a.dry_run:
                print("dry run: data/ untouched"); return 0
            if ch:
                swap_in(sd, data)
            print("OK"); return 0
        except Fail as e:
            print("FAIL:", e, "(data/ untouched)"); return 1

if __name__ == "__main__":
    sys.exit(main())
