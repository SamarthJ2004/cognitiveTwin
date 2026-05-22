"""
daemon_appswitch.py — App switching tracker

Uses osascript to poll the frontmost app every second.

Run in a separate terminal:
    python daemon_appswitch.py

Data saved to: ~/.cognitivetwin/appswitch.json
"""

import json
import signal
import subprocess
import sys
import time
from collections import defaultdict, Counter
from datetime import datetime
from pathlib import Path

DATA_DIR = Path.home() / ".cognitivetwin"
DATA_DIR.mkdir(exist_ok=True)
OUTPUT = DATA_DIR / "appswitch.json"

POLL_INTERVAL = 1.0   # seconds between checks
SAVE_INTERVAL = 60    # save every N seconds
MIN_DURATION = 3     # ignore focus shorter than this (accidental clicks)

state = {
    "current_app": None,
    "current_start": None,
    "sessions": [],
    "switch_times": [],
}


def get_active_app():
    try:
        result = subprocess.run(
            ["osascript", "-e", 'tell application "System Events" to get name of first process whose frontmost is true'],
            capture_output=True, text=True, timeout=2
        )
        name = result.stdout.strip()
        return name if name else None
    except Exception:
        return None


def on_switch(new_app):
    now = time.time()

    if state["current_app"] and state["current_start"]:
        duration = now - state["current_start"]
        if duration >= MIN_DURATION:
            state["sessions"].append({
                "app": state["current_app"],
                "duration_s": round(duration, 1),
                "hour": datetime.fromtimestamp(state["current_start"]).hour,
                "date": datetime.fromtimestamp(state["current_start"]).strftime("%Y-%m-%d"),
            })
            print(
                f"  \033[90m{datetime.now().strftime('%H:%M:%S')}\033[0m"
                f"  {state['current_app']} ({duration:.0f}s)"
                f"  →  {new_app}"
            )

    state["switch_times"].append(now)
    state["current_app"] = new_app
    state["current_start"] = now


def save():
    sessions = state["sessions"]
    if not sessions:
        return None

    time_per_app = defaultdict(float)
    for s in sessions:
        time_per_app[s["app"]] += s["duration_s"]
    ranked = sorted(time_per_app.items(), key=lambda x: x[1], reverse=True)

    durations = [s["duration_s"] for s in sessions]
    avg_duration = sum(durations) / len(durations)

    switches_by_hour = defaultdict(int)
    for ts in state["switch_times"]:
        switches_by_hour[datetime.fromtimestamp(ts).hour] += 1

    app_list = [s["app"] for s in sessions[-100:]]
    sequences = [f"{app_list[i]} → {app_list[i + 1]}" for i in range(len(app_list) - 1)]
    top_sequences = Counter(sequences).most_common(10)

    summary = {
        "top_apps_by_time": [
            {"app": app, "minutes": round(secs / 60, 1)}
            for app, secs in ranked[:15]
        ],
        "avg_session_seconds": round(avg_duration, 1),
        "total_switches": len(sessions),
        "switches_by_hour": dict(switches_by_hour),
        "top_app_sequences": [
            {"sequence": seq, "count": cnt}
            for seq, cnt in top_sequences
        ],
        "attention_style": _classify(avg_duration),
        "last_updated": datetime.now().isoformat(),
    }

    OUTPUT.write_text(json.dumps(summary, indent=2))
    return summary


def _classify(avg_s):
    if avg_s < 45:
        return "highly fragmented — very frequent context switching"
    if avg_s < 120:
        return "moderately fragmented — frequent task switching"
    if avg_s < 300:
        return "moderate focus — some switching"
    return "focused — stays in one app for extended periods"


def shutdown(sig, frame):
    print("\n  Shutting down...")
    # close current session
    if state["current_app"] and state["current_start"]:
        duration = time.time() - state["current_start"]
        if duration >= MIN_DURATION:
            state["sessions"].append({
                "app": state["current_app"],
                "duration_s": round(duration, 1),
                "hour": datetime.fromtimestamp(state["current_start"]).hour,
                "date": datetime.fromtimestamp(state["current_start"]).strftime("%Y-%m-%d"),
            })

    summary = save()
    if summary:
        print(f"  {len(state['sessions'])} sessions saved → {OUTPUT}")
        print(f"  Attention style: {summary['attention_style']}")
    else:
        print("  No sessions recorded.")
    sys.exit(0)


def main():
    print("  \033[94mApp Switch Tracker\033[0m  (polling every 1s via osascript)")
    print(f"  Output: {OUTPUT}")
    print("  Press Ctrl+C to stop.\n")

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    current = get_active_app()
    if not current:
        print("  Could not read frontmost app.")
        print("  Grant Accessibility access: System Settings → Privacy → Accessibility → Terminal")
        sys.exit(1)

    state["current_app"] = current
    state["current_start"] = time.time()
    print(f"  Tracking started. Current app: \033[93m{current}\033[0m\n")

    last_save = time.time()

    while True:
        time.sleep(POLL_INTERVAL)

        active = get_active_app()
        if active and active != state["current_app"]:
            on_switch(active)

        if time.time() - last_save >= SAVE_INTERVAL:
            save()
            last_save = time.time()


if __name__ == "__main__":
    main()
