"""
Tracks TIMING between keystrokes, NOT which keys are pressed.
Records:
  - typing speed (WPM estimate from keystroke cadence)
  - correction rate (backspace frequency)
  - hesitations (pauses > 1.5s mid-sentence)
  - burst vs steady typing style

Permissions: Accessibility access required.
    → System Settings > Privacy & Security > Accessibility → add Terminal

Run in a separate terminal (keep it running):
    python daemon_typing.py

Data saved to: ~/.cognitivetwin/typing.json
Install dependency: pip install pynput
"""

import json
import signal
import sys
import time
from collections import deque
from datetime import datetime
from pathlib import Path

from pynput import keyboard

DATA_DIR = Path.home() / ".cognitivetwin"
DATA_DIR.mkdir(exist_ok=True)
OUTPUT = DATA_DIR / "typing.json"

HESITATION_THRESHOLD = 1.5   # seconds — pause longer than this = hesitation
BURST_MIN_KEYS = 5     # minimum keys in a row to count as a burst
SAVE_INTERVAL = 60    # save to file every N seconds
SESSION_GAP = 30    # gap > 30s = new typing session

state = {
    "last_key_time": None,
    "intervals": deque(maxlen=500),   # time between keystrokes (seconds)
    "backspace_count": 0,
    "total_keys": 0,
    "hesitations": [],                  # list of hesitation durations
    "current_burst": 0,
    "bursts": [],                  # list of burst lengths

    "session_start": None,
    "sessions": [],

    "last_save": time.time(),
}


def on_press(key):
    now = time.time()

    if key == keyboard.Key.backspace:
        # key_type = "backspace"
        state["backspace_count"] += 1
    elif key == keyboard.Key.space or key == keyboard.Key.enter:
        pass
        # key_type = "word_boundary"
    elif hasattr(key, "char") and key.char:
        pass
        # key_type = "character"
    else:
        # key_type = "modifier"   # shift, ctrl, etc — skip
        return

    state["total_keys"] += 1

    if state["last_key_time"] is not None:
        interval = now - state["last_key_time"]

        if interval > SESSION_GAP:
            # long gap = new session — save the previous one
            _close_session()

        elif interval > HESITATION_THRESHOLD:
            # mid-typing pause = hesitation
            state["hesitations"].append(round(interval, 2))
            state["current_burst"] = 0   # burst broken

        else:
            # normal keystroke — record interval
            state["intervals"].append(interval)
            state["current_burst"] += 1

            if state["current_burst"] >= BURST_MIN_KEYS:
                state["bursts"].append(state["current_burst"])

    else:
        # first key of a session
        state["session_start"] = now

    state["last_key_time"] = now

    # periodic save
    if now - state["last_save"] > SAVE_INTERVAL:
        _save()
        state["last_save"] = now


def _close_session():
    intervals = list(state["intervals"])
    if len(intervals) < 10:
        # too few keystrokes to be meaningful
        _reset_session()
        return

    session = _compute_session_metrics(intervals)
    state["sessions"].append(session)

    _reset_session()


def _reset_session():
    state["intervals"].clear()
    state["backspace_count"] = 0
    state["total_keys"] = 0
    state["hesitations"] = []
    state["current_burst"] = 0
    state["bursts"] = []
    state["session_start"] = None
    state["last_key_time"] = None


def _compute_session_metrics(intervals):
    """
    Turn raw keystroke intervals into readable cognitive metrics.
    WPM estimate: average chars per second * 60 / 5
    (5 chars = 1 word, standard WPM convention)
    """
    if not intervals:
        return {}

    avg_interval = sum(intervals) / len(intervals)
    chars_per_sec = 1 / avg_interval if avg_interval > 0 else 0
    wpm_estimate = round(chars_per_sec * 60 / 5, 1)

    # correction rate = backspaces / total keys
    correction_rate = (
        state["backspace_count"] / state["total_keys"]
        if state["total_keys"] > 0 else 0
    )

    # hesitation stats
    hesitations = state["hesitations"]
    avg_hesitation = (
        sum(hesitations) / len(hesitations) if hesitations else 0
    )

    # burst stats — long bursts = flow state
    bursts = state["bursts"]
    avg_burst = sum(bursts) / len(bursts) if bursts else 0

    return {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "wpm_estimate": wpm_estimate,
        "correction_rate": round(correction_rate, 3),
        "hesitation_count": len(hesitations),
        "avg_hesitation_s": round(avg_hesitation, 2),
        "avg_burst_length": round(avg_burst, 1),
        "total_keys": state["total_keys"],
    }


def _save():
    # include current in-progress session
    intervals = list(state["intervals"])
    all_sessions = list(state["sessions"])
    if len(intervals) >= 10:
        all_sessions.append(_compute_session_metrics(intervals))

    if not all_sessions:
        return

    # aggregate across sessions
    wpm_values = [s["wpm_estimate"] for s in all_sessions if s.get("wpm_estimate")]
    correction_rates = [s["correction_rate"] for s in all_sessions if "correction_rate" in s]
    hesitation_counts = [s["hesitation_count"] for s in all_sessions if "hesitation_count" in s]
    burst_lengths = [s["avg_burst_length"] for s in all_sessions if s.get("avg_burst_length")]

    summary = {
        "sessions_today": len(all_sessions),
        "avg_wpm": round(sum(wpm_values) / len(wpm_values), 1) if wpm_values else None,
        "avg_correction_rate": round(sum(correction_rates) / len(correction_rates), 3) if correction_rates else None,
        "avg_hesitations_per_session": round(
            sum(hesitation_counts) / len(hesitation_counts), 1
        ) if hesitation_counts else None,
        "avg_burst_length": round(sum(burst_lengths) / len(burst_lengths), 1) if burst_lengths else None,

        # cognitive interpretation — what the numbers mean
        "typing_style": _classify_typing_style(
            sum(wpm_values) / len(wpm_values) if wpm_values else 0,
            sum(correction_rates) / len(correction_rates) if correction_rates else 0,
            sum(hesitation_counts) / len(hesitation_counts) if hesitation_counts else 0,
        ),
        "recent_sessions": all_sessions[-5:],   # last 5 for context
        "last_updated": datetime.now().isoformat(),
    }

    OUTPUT.write_text(json.dumps(summary, indent=2))


def _classify_typing_style(avg_wpm, avg_correction, avg_hesitations):
    """
    Heuristic: map typing metrics to a cognitive style description.
    Fast + few corrections + few hesitations = confident, clear thinker
    Slow + many corrections = perfectionist or uncertain
    Fast + many corrections = impulsive, edits after the fact
    Many hesitations = deliberate, thinks before typing
    """
    if avg_wpm > 70 and avg_correction < 0.05 and avg_hesitations < 3:
        return "fast and decisive — types with confidence, rarely second-guesses"
    elif avg_wpm < 40 and avg_correction > 0.10:
        return "deliberate and self-editing — thinks carefully, corrects frequently"
    elif avg_wpm > 60 and avg_correction > 0.12:
        return "impulsive then corrective — types quickly but revises a lot"
    elif avg_hesitations > 8:
        return "pause-heavy — frequently stops to think before continuing"
    elif avg_correction > 0.15:
        return "highly self-critical — very high correction rate suggests perfectionism"
    else:
        return "moderate — balanced typing style"


def shutdown(sig, frame):
    print("\n  Saving final data...")
    _close_session()
    _save()
    print(f"  Data saved to {OUTPUT}")
    sys.exit(0)


def main():
    print("  \033[94mTyping Pattern Tracker running\033[0m")
    print("  Tracking: speed, corrections, hesitations — NOT actual keys")
    print(f"  Saving to: {OUTPUT}")
    print("  Requires Accessibility permission for Terminal in System Settings.")
    print("  Press Ctrl+C to stop.\n")

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    with keyboard.Listener(on_press=on_press) as listener:
        listener.join()


if __name__ == "__main__":
    main()
