"""
collect behavioural data (MacOS only)

Brave History
Bash History
Zsh History
App Usage
Sleep Wake Cycles
App Switching Daemon
Typing Daemon

Run separately from main.py:
    python collect.py your_name
"""

import json
import sys
from urllib.parse import urlparse, parse_qs
from datetime import datetime, timedelta
from pathlib import Path
import sqlite3
import shutil
import re
from app.data_analysis import analyze_behaviour
from collect_api import get_github_data
import app.db as db
from collections import Counter
import subprocess

TODAY = datetime.now().strftime("%Y-%m-%d")
DATA_DIR = Path.home() / ".cognitivetwin"

SENSITIVE_PATTERNS = [
    r"api[_-]?key",
    r"token",
    r"secret",
    r"password",
    r"passwd",
    r"authorization",
    r"bearer",
    r"sk-[A-Za-z0-9]+",      # OpenAI-like keys
    r"ghp_[A-Za-z0-9]+",     # GitHub tokens
    r"AKIA[0-9A-Z]+",        # AWS keys
]

APP_NAME_MAP = {
    "com.apple.dt.Xcode": "Xcode",
    "com.google.Chrome": "Chrome",
    "com.brave.Browser": "Brave",
    "com.microsoft.VSCode": "VS Code",
    "com.apple.Terminal": "Terminal",
    "com.tinyspeck.slackmacgap": "Slack",
    "com.spotify.client": "Spotify",
    "com.apple.MobileSMS": "Messages",
    "com.apple.mail": "Mail",
    "com.googlecode.iterm2": "iTerm",
    "tv.jellyfin.player": "Jellyfin Media Player",
    "com.apple.Music": "Apple Music",
    "com.apple.finder": "Finder",
    "com.google.antigravity": "Antigravity",
    "org.videolan.vlc": "VLC",
    "com.colliderli.iina": "IINA",
    "com.apple.systempreferences": "System Settings",
    "org.qbittorrent.qBittorrent": "qBittorrent",
    "net.whatsapp.WhatsApp": "WhatsApp"
}


def step(label): print(f"\n  \033[94m→\033[0m  {label}")
def ok(label): print(f"  \033[92m✓\033[0m  {label}")
def skip(label): print(f"  \033[90m–\033[0m  {label}")
def warn(label): print(f"  \033[93m⚡\033[0m {label}")
def err(label): print(f"  \033[91m✗\033[0m  {label}")


def _read_sqlite_history(src_path, query, params=()):
    """
    we need to first copy the files to a temporary
    location as the browsers lock these files while
    running so we can't read them directly
    """
    tmp = Path("/tmp/_history_copy")
    shutil.copy2(src_path, tmp)      # preserves metadata

    try:
        conn = sqlite3.connect(tmp)
        rows = conn.execute(query, params).fetchall()
        conn.close()
    finally:
        tmp.unlink(missing_ok=True)
    return rows


# was required if using urls
def _prettify_google_url(url):
    # else there is a lot of other data like anti bot, session token, click tracking, state , analytics
    try:
        parsed = urlparse(url)

        if "google." in parsed.netloc and parsed.path == "/search":
            query = parse_qs(parsed.query).get("q", [""])[0]
            url = f"https://www.google.com/search?q={query}"
        return url

    except Exception:
        return url


def get_brave_history(days=30, limit=200):
    # for Default Profile only
    src = Path.home() / "Library/Application Support/BraveSoftware/Brave-Browser/Default/History"

    if not src.exists():
        return []

    # Chrome/Brave store time as: microseconds since 1601-01-01 00:00:00 UTC
    chrome_epoch = datetime(1601, 1, 1)

    since = datetime.now() - timedelta(days=days)
    since_chrome = int((since - chrome_epoch).total_seconds() * 1_000_000)

    # rows = _read_sqlite_history(
    #     src,
    #     """
    #     SELECT url, title
    #     FROM urls
    #     WHERE last_visit_time > ? AND title != ''
    #     ORDER BY last_visit_time DESC
    #     LIMIT ?
    #     """,
    #     (since_chrome, limit)
    # )
    # return [
    #     {"url": _prettify_google_url(r[0]), "title": r[1]} for r in rows if r[1]
    # ]

    # only return the titles
    rows = _read_sqlite_history(
        src,
        """
        SELECT title
        FROM urls
        WHERE last_visit_time > ? AND title != ''
        ORDER BY last_visit_time DESC
        LIMIT ?
        """,
        (since_chrome, limit)
    )

    title_freq = Counter([r[0] for r in rows if r[0]])
    return [{"title": t, "visits": c} for t, c in title_freq.most_common(50)]


def _sanitize_command(cmd):
    # to remove api keys, passwords and sensitive data from the terminal history
    lower = cmd.lower()

    for pattern in SENSITIVE_PATTERNS:
        if re.search(pattern, lower, re.IGNORECASE):
            return "[REDACTED SENSITIVE COMMAND]"

    return cmd


def get_terminal_history(limit=300):
    zsh = Path.home() / ".zsh_history"
    bash = Path.home() / ".bash_history"

    src = zsh if zsh.exists() else (bash if bash.exists() else None)

    if not src:
        return []

    commands = src.read_text(errors="ignore").splitlines()

    cleaned = [
        _sanitize_command(cmd)
        for cmd in commands[-limit:]
    ]

    return cleaned


def get_app_usage():
    src = Path.home() / "Library/Application Support/Knowledge/knowledgeC.db"

    if not src.exists():
        return []

    try:
        rows = _read_sqlite_history(
            src,
            """
            SELECT
                ZVALUESTRING AS app,
                ROUND(SUM(ZENDDATE - ZSTARTDATE)/ 60.0, 2) AS minutes
            FROM ZOBJECT
            WHERE ZSTREAMNAME = '/app/usage'
            GROUP BY ZVALUESTRING
            ORDER BY minutes DESC
            LIMIT 20;
            """
        )
        return [{"app": APP_NAME_MAP.get(r[0], r[0]), "minutes": int(r[1])} for r in rows if (int(r[1]) > 5)]
    except Exception as e:
        print("Error: ", e)
        return []


def get_running_apps():
    return


def get_sleep_wake_data(days=7):
    """
    Reads macOS power management logs via `pmset -g log`.
    Extracts sleep and wake events to calculate:
    - average sleep time
    - average wake time
    - sleep duration
    - sleep consistency (do they sleep at the same time?)

    No permissions needed — pmset is a standard macOS tool.
    """
    result = subprocess.run(
        "pmset -g log | grep -E 'Entering Sleep state|Wake from Deep Idle' | grep -vi darkwake",
        shell=True,
        capture_output=True,
        text=True
    )
    lines = result.stdout.splitlines()

    since = datetime.now() - timedelta(days=days)
    events = []

    for line in lines:
        # pmset log format: "2024-01-15 23:45:12 +0530 Sleep ..."
        # or:               "2024-01-15 07:23:45 +0530 Wake  ..."
        match = re.match(
            r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) [+-]\d{4}\s+(Sleep|Wake)",
            line
        )
        if not match:
            continue

        try:
            dt = datetime.strptime(match.group(1), "%Y-%m-%d %H:%M:%S")
            event_type = match.group(2)
        except ValueError:
            continue

        if dt >= since:
            events.append({"type": event_type, "time": dt})

    if not events:
        return None

    # pair sleep/wake events
    sleep_sessions = []
    last_sleep = None

    for event in events:
        if event["type"] == "Sleep" and last_sleep == None:
            last_sleep = event["time"]
        elif event["type"] == "Wake" and last_sleep:
            duration_hrs = (event["time"] - last_sleep).total_seconds() / 3600
            if 2 < duration_hrs < 14:   # filter out short naps and outliers
                sleep_sessions.append({
                    "sleep_time": last_sleep.strftime("%H:%M"),
                    "wake_time": event["time"].strftime("%H:%M"),
                    "sleep_minutes": last_sleep.hour * 60 + last_sleep.minute,
                    "wake_minute": event["time"].hour * 60 + event["time"].minute,
                    "duration_hrs": round(duration_hrs, 2),
                })
            last_sleep = None

    if not sleep_sessions:
        return None

    # need to update this with sin cos based average for correct value
    avg_sleep_minute = sum(s["sleep_minutes"] for s in sleep_sessions) / len(sleep_sessions)
    avg_wake_minute = sum(s["wake_minute"] for s in sleep_sessions) / len(sleep_sessions)
    avg_duration = sum(s["duration_hrs"] for s in sleep_sessions) / len(sleep_sessions)

    # consistency = low std deviation in sleep time = consistent schedule
    import statistics

    sleep_hours = [
        s["sleep_minutes"] / 60
        for s in sleep_sessions
    ]

    consistency = (
        "consistent"
        if len(sleep_hours) > 2 and statistics.stdev(sleep_hours) < 1.5
        else "irregular"
    )

    def minutes_to_hhmm(minutes):
        hours = int(minutes // 60) % 24
        mins = int(minutes % 60)
        return f"{hours:02d}:{mins:02d}"

    avg_sleep_hr = avg_sleep_minute / 60
    avg_wake_hr = avg_wake_minute / 60

    return {
        "sessions": sleep_sessions[-7:],
        "avg_sleep_time": minutes_to_hhmm(avg_sleep_minute),
        "avg_wake_time": minutes_to_hhmm(avg_wake_minute),
        "avg_duration_hrs": round(avg_duration, 2),
        "schedule": consistency,
        "chronotype":
            "night owl"
            if avg_sleep_hr >= 23 or avg_sleep_hr <= 3
            else (
                "early riser"
                if avg_sleep_hr <= 22 and avg_wake_hr <= 7
                else "average"
        ),
    }


def get_daemon_data():
    # read appswitch.json and typing.json
    result = {}
    for name, filename in [("app_switching", "appswitch.json"), ("typing_patterns", "typing.json"), ("music", "music.json")]:
        path = DATA_DIR / filename
        if path.exists():
            try:
                result[name] = json.loads(path.read_text())
            except Exception:
                pass
    return result if result else None


def store_signals(session, user_id, signals):
    # store behavioral signals to Neo4j with self_type='behavioral'

    for b in signals.get("beliefs", []):
        db.save_belief(session, user_id, text=b["text"], self_type="behavioral", confidence=b.get(
            "confidence", 0.6), date=TODAY)

    for p in signals.get("patterns", []):
        db.save_pattern(session, user_id, text=p, self_type="behavioral",
                        source="activity_collect", date=TODAY)

    for t in signals.get("topics", []):
        db.save_topic(session, user_id, name=t,
                      self_type="behavioral", date=TODAY)

    for c in signals.get("contradictions", []):
        db.save_contradiction(session, user_id, text=c["text"],
                              self_a=c.get("self_a", "stated"), self_b=c.get("self_b", "behavioral"),
                              confidence=c.get("confidence", 0.6), date=TODAY)


def run_collection(user_id):
    print(f"\n  Collecting behavioral data for: \033[94m{user_id}\033[0m")
    print(f"  \033[90m{TODAY}\033[0m\n")

    data_summary = {}
    data_summary["browser_titles"] = get_brave_history()
    data_summary["terminal_commands"] = get_terminal_history()
    data_summary["app_usage"] = get_app_usage()
    data_summary["sleep_wake"] = get_sleep_wake_data()
    data_summary["github"] = get_github_data()
    data_summary.update(get_daemon_data())

    if not data_summary:
        err("No data collected.")
        return

    # get stated profile for contradiction comparison
    with db.driver.session() as session:
        db.ensure_user(session, user_id)
        stated_profile = db.get_profile(session, user_id)
        stated_text = db.format_profile(
            stated_profile) if stated_profile else "No stated profile yet."

        step("Analyzing behavioral patterns with OpenAI...")
        try:
            signals = analyze_behaviour.run_pipeline(data_summary, stated_text)
        except Exception as e:
            err(f"Analysis failed: {e}")
            return

        step("Storing to graph...")
        store_signals(session, user_id, signals)
        ok("Behavioral layer updated")

    print("\n\033[93mBehavioral summary:\033[0m")
    print(f"  {signals.get('summary', '')}")

    contradictions = signals.get("contradictions", [])
    if contradictions:
        print("\n\033[91mContradictions with your stated self:\033[0m")
        for c in contradictions:
            conf = c.get("confidence", 0)
            warn(f"({conf:.0%} confidence) {c['text']}")
    else:
        print(
            "\n  \033[90mNo contradictions detected with stated profile.\033[0m")

    print()


if __name__ == "__main__":
    user_id = sys.argv[1] if len(
        sys.argv) > 1 else input("  Your name: ").strip()
    if not user_id:
        print("  Name required.")
        sys.exit(1)
    run_collection(user_id)
    db.driver.close()
