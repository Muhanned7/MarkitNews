#!/usr/bin/env python3
"""
tester_inbox_check.py — the QA/UX tester's inbox for developer input.

Mirror of watch_tester_feedback.py, but in the other direction and with its own
state file, so the two watchers never consume each other's alerts.

Usage
  python3 scripts/tester_inbox_check.py          # report new developer input (exit 1 if any, 0 if none)
  python3 scripts/tester_inbox_check.py --ack    # tester just wrote: re-baseline silently
  python3 scripts/tester_inbox_check.py --status # show what is being tracked

Output on change: a unified diff of exactly what was added/changed since the
last check, per file, plus any new ENTRY headings and QA rows whose
Status / Resolution moved. Also lists source files the developer added,
modified or removed under app/, backend/, lib/, scripts/ (--ack never resets
the code index, so code changes are not lost when the tester writes).
"""
import sys, os, json, hashlib, difflib, csv, io, re
from datetime import datetime
from pathlib import Path

if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

BASE = Path(__file__).resolve().parent.parent
STATE = BASE / ".tester_inbox_state.json"
WATCHED = ["TESTER_COMMUNICATIONS.md", "QA_TASKS.md", "QA_TASKS.csv",
           "QPM_COMMUNICATIONS.md", "QPM_TASKS.md", "QPM_FEATURE_REQUESTS.md",
           "RISK_COMMUNICATIONS.md", "RISK_TASKS.md", "RISK_FEATURE_REQUESTS.md",
           "QRA_COMMUNICATIONS.md", "QRA_TASKS.md", "QRA_FEATURE_REQUESTS.md"]
MAX_DIFF_LINES = 200
# Developer code changes are reported as a file list (not full diffs).
CODE_DIRS = ["app", "backend", "lib", "scripts", "qa_fixtures"]
CODE_FILES = ["package.json", "next.config.mjs", "DOCUMENTATION.md", "README.md", "AGENTS.md"]
CODE_EXT = {".js", ".jsx", ".ts", ".tsx", ".css", ".py", ".json", ".mjs", ".yml", ".yaml", ".md", ".sql"}
SKIP = {"node_modules", ".next", "venv", ".venv", "__pycache__", "logs", ".git"}
SELF = {"scripts/tester_inbox_check.py"}


def code_index():
    idx = {}
    paths = [BASE / f for f in CODE_FILES]
    for d in CODE_DIRS:
        root = BASE / d
        if not root.exists():
            continue
        # os.walk with in-place pruning so venv/node_modules are never entered
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [x for x in dirnames if x not in SKIP and not x.startswith(".")]
            for fn in filenames:
                p = Path(dirpath) / fn
                if p.suffix in CODE_EXT:
                    paths.append(p)
    for p in paths:
        if p.exists():
            rel = p.relative_to(BASE).as_posix()
            if rel in SELF:
                continue
            st = p.stat()
            idx[rel] = [int(st.st_mtime), st.st_size]
    return idx


def code_changes(old, new):
    added = sorted(set(new) - set(old))
    removed = sorted(set(old) - set(new))
    modified = sorted(k for k in set(old) & set(new) if old[k] != new[k])
    return added, modified, removed


def read(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8", errors="replace")
    except FileNotFoundError:
        return ""


def sha(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def load():
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save(st):
    STATE.write_text(json.dumps(st, indent=1), encoding="utf-8")


def snapshot():
    return {n: read(BASE / n) for n in WATCHED}


def baseline(st=None):
    st = {} if st is None else st
    now = datetime.now().isoformat(timespec="seconds")
    for n, txt in snapshot().items():
        st[n] = {"hash": sha(txt), "content": txt, "seen_at": now}
    save(st)


def csv_rows(txt):
    try:
        return {r.get("Task_ID"): r for r in csv.DictReader(io.StringIO(txt)) if r.get("Task_ID")}
    except Exception:
        return {}


def check() -> int:
    st = load()
    if not st:
        baseline()
        print("[tester-inbox] baseline created — no prior state to compare against.")
        return 0
    found = False
    now = datetime.now().isoformat(timespec="seconds")
    for n, cur in snapshot().items():
        prev = st.get(n, {}).get("content", "")
        if sha(cur) == st.get(n, {}).get("hash"):
            continue
        found = True
        print("=" * 72)
        print(f"NEW DEVELOPER INPUT: {n}   (detected {now})")
        print("=" * 72)
        diff = list(difflib.unified_diff(prev.splitlines(), cur.splitlines(),
                                         "before", "after", n=1, lineterm=""))
        added_entries = [l[1:] for l in diff if l.startswith("+") and re.match(r"\+#+\s*\[((QPM|RISK|QRA)-)?ENTRY", l)]
        if added_entries:
            print("New entries:")
            for e in added_entries:
                print("  •", e.strip())
        if n.endswith(".csv"):
            a, b = csv_rows(prev), csv_rows(cur)
            for tid, row in b.items():
                old = a.get(tid)
                if old is None:
                    print(f"  + new task {tid}: {row.get('Test_Scenario')}")
                    continue
                for k in ("Status", "Resolution", "Tester_Notes", "UI_UX_Feedback"):
                    if (old.get(k) or "") != (row.get(k) or ""):
                        print(f"  ~ {tid}.{k}: {old.get(k)!r} -> {row.get(k)!r}")
        print("--- diff ---")
        print("\n".join(diff[:MAX_DIFF_LINES]))
        if len(diff) > MAX_DIFF_LINES:
            print(f"... ({len(diff) - MAX_DIFF_LINES} more diff lines; read the file)")
        st[n] = {"hash": sha(cur), "content": cur, "seen_at": now}

    # ---- developer code changes (file list) ----
    new_idx = code_index()
    old_idx = st.get("_code")
    if old_idx is None:
        print(f"[tester-inbox] code index initialised ({len(new_idx)} files).")
    else:
        added, modified, removed = code_changes(old_idx, new_idx)
        if added or modified or removed:
            found = True
            print("=" * 72)
            print(f"DEVELOPER CODE CHANGES   (detected {now})")
            print("=" * 72)
            for tag, lst in (("+ added", added), ("~ modified", modified), ("- removed", removed)):
                for f in lst:
                    print(f"  {tag}: {f}")
    st["_code"] = new_idx

    save(st)
    if found:
        return 1
    print(f"[tester-inbox {now}] no new developer input.")
    return 0


if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv) > 1 else ""
    if arg == "--ack":
        # Race guard: if the developer wrote into a watched file between the last
        # check and this ack, surface it instead of silently absorbing it.
        st = load()
        for n, cur in snapshot().items():
            prev = st.get(n, {}).get("content", "")
            added = [l[1:] for l in difflib.unified_diff(prev.splitlines(), cur.splitlines(), lineterm="", n=0)
                     if l.startswith("+") and not l.startswith("+++")]
            dev = [l for l in added if re.search(r"Author\W*:?\W*.*(Developer)", l)]
            if dev:
                heads = [l for l in added if l.startswith("### [ENTRY")]
                print(f"!! DEVELOPER INPUT ABSORBED BY ACK in {n}: " + "; ".join(heads or dev))
        baseline(st); print("[tester-inbox] re-baselined after tester write.")
    elif arg == "--status":
        for n, v in load().items():
            if n == "_code":
                print(f"code index: {len(v)} files")
            else:
                print(f"{n}: seen_at={v.get('seen_at')} hash={v.get('hash','')[:12]}")
    else:
        sys.exit(check())
