#!/usr/bin/env python3
"""
watch_tester_feedback.py
Real-time watcher and alert tool for QA_TASKS.md, QA_TASKS.csv, and TESTER_COMMUNICATIONS.md.
Detects when the manual tester or UI/UX consultant adds feedback, highlights diffs, and alerts the AI assistant.
Immediately exits upon detecting changes so background task completion triggers an instant agent wake-up.
"""

import os
import sys
import time
import json
import hashlib
from datetime import datetime
from pathlib import Path

if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

BASE_DIR = Path(__file__).resolve().parent.parent
STATE_FILE = BASE_DIR / ".feedback_watcher_state.json"

WATCHED_FILES = [
    BASE_DIR / "QA_TASKS.md",
    BASE_DIR / "QA_TASKS.csv",
    BASE_DIR / "TESTER_COMMUNICATIONS.md",
    BASE_DIR / "QPM_TASKS.md",
    BASE_DIR / "QPM_COMMUNICATIONS.md",
    BASE_DIR / "QPM_FEATURE_REQUESTS.md",
    BASE_DIR / "RISK_TASKS.md",
    BASE_DIR / "RISK_COMMUNICATIONS.md",
    BASE_DIR / "RISK_FEATURE_REQUESTS.md",
    BASE_DIR / "QRA_TASKS.md",
    BASE_DIR / "QRA_COMMUNICATIONS.md",
    BASE_DIR / "QRA_FEATURE_REQUESTS.md",
]

def compute_hash(filepath: Path) -> str:
    if not filepath.exists():
        return ""
    hasher = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(8192):
            hasher.update(chunk)
    return hasher.hexdigest()

def read_lines(filepath: Path):
    if not filepath.exists():
        return []
    try:
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            return f.readlines()
    except Exception:
        return []

def load_state() -> dict:
    if STATE_FILE.exists():
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def save_state(state: dict):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)

def sync_baseline():
    """Takes a fresh snapshot of current file states so only future changes trigger an alert."""
    state = {}
    for f in WATCHED_FILES:
        if f.exists():
            state[f.name] = {
                "hash": compute_hash(f),
                "mtime": f.stat().st_mtime,
                "line_count": len(read_lines(f)),
                "last_alerted": datetime.now().isoformat()
            }
    save_state(state)
    return state

def check_for_changes() -> list:
    """Checks all watched files for modifications compared to saved state."""
    state = load_state()
    notifications = []
    
    for f in WATCHED_FILES:
        if not f.exists():
            continue
        name = f.name
        curr_hash = compute_hash(f)
        curr_mtime = f.stat().st_mtime
        curr_lines = read_lines(f)
        
        file_state = state.get(name)
        if not file_state:
            state[name] = {
                "hash": curr_hash,
                "mtime": curr_mtime,
                "line_count": len(curr_lines),
                "last_alerted": datetime.now().isoformat()
            }
            continue
            
        if curr_hash != file_state.get("hash"):
            notifications.append({
                "file": name,
                "path": str(f),
                "detected_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "total_lines": len(curr_lines),
                "previous_lines": file_state.get("line_count", 0),
                "lines_added": len(curr_lines) - file_state.get("line_count", 0)
            })
            
            state[name] = {
                "hash": curr_hash,
                "mtime": curr_mtime,
                "line_count": len(curr_lines),
                "last_alerted": datetime.now().isoformat()
            }
            
    if notifications:
        save_state(state)
        
    return notifications

def display_alert(notif: dict):
    print("=" * 70)
    print(f"[ALERT: TESTER / CONSULTANT FEEDBACK DETECTED]")
    print(f"File:        {notif['file']}")
    print(f"Timestamp:   {notif['detected_at']}")
    print(f"Line Change: +{notif['lines_added']} lines (Total: {notif['total_lines']})")
    print("=" * 70)
    
    # Print the most recent lines of the modified file
    filepath = Path(notif['path'])
    lines = read_lines(filepath)
    tail_count = min(30, len(lines))
    print(f"--- Recent Content in {notif['file']} (Last {tail_count} lines) ---")
    print("".join(lines[-tail_count:]))
    print("=" * 70)
    sys.stdout.flush()

def run_check_mode():
    changes = check_for_changes()
    if changes:
        for c in changes:
            display_alert(c)
        return 1
    else:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] No new input detected in watched communication and task files.")
        return 0

def run_daemon_mode(interval_sec=4, exit_on_alert=True):
    # Take a fresh baseline when daemon is turned ON so we only alert on future tester edits
    sync_baseline()
    print(f"[*] Started Feedback Watcher Daemon. Monitoring {len(WATCHED_FILES)} files every {interval_sec}s...")
    for f in WATCHED_FILES:
        print(f"    - {f.name}")
    print(f"[*] Mode: Instant wake-up enabled (will exit immediately upon detecting tester feedback).")
    sys.stdout.flush()
    
    try:
        while True:
            changes = check_for_changes()
            if changes:
                for c in changes:
                    display_alert(c)
                if exit_on_alert:
                    print(f"\n[!] Tester feedback detected. Terminating process to wake up AI assistant immediately.")
                    sys.stdout.flush()
                    sys.exit(0)
            time.sleep(interval_sec)
    except KeyboardInterrupt:
        print("\n[*] Feedback Watcher stopped.")

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--daemon":
        run_daemon_mode(exit_on_alert=True)
    elif len(sys.argv) > 1 and sys.argv[1] == "--sync":
        sync_baseline()
        print("[*] Baseline synced with current files on disk.")
    else:
        sys.exit(run_check_mode())
