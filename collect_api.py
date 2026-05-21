"""
collect API based behavioural data

Sources:
  - GitHub
  - Spotify
  - Sleep/Wake

Run separately from main.py:
    python collect_api.py your_name

Setup:
  GitHub  → create token at github.com/settings/tokens (read:user, repo)
            add GITHUB_TOKEN and GITHUB_USERNAME to .env
  Spotify → create app at developer.spotify.com
            add SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET, SPOTIFY_REDIRECT_URI to .env
            first run will open browser for OAuth — after that it caches the token
"""

import os
from datetime import datetime, timedelta
from pathlib import Path
from collections import Counter
import re
import requests
from dotenv import load_dotenv
from openai import OpenAI
import spotipy
from spotipy.oauth2 import SpotifyOAuth
import subprocess
import json

load_dotenv()

TODAY = datetime.now().strftime("%Y-%m-%d")
DATA_DIR = Path.home() / ".cognitivetwin"
DATA_DIR.mkdir(exist_ok=True)

ai = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


def step(label): print(f"\n  \033[94m→\033[0m  {label}")
def ok(label): print(f"  \033[92m✓\033[0m  {label}")
def skip(label): print(f"  \033[90m–\033[0m  {label}")
def warn(label): print(f"  \033[93m⚡\033[0m {label}")
def err(label): print(f"  \033[91m✗\033[0m  {label}")


def get_github_data():
    """
    Fetches:
    - repos (name, language, topics, last pushed)
    - language distribution (what they actually build in)
    - recent events (push, PR, issue — tells you work patterns)
    - commit hour distribution (when they actually code)
    """
    username = os.getenv("GITHUB_USERNAME")
    token = os.getenv("GITHUB_TOKEN")

    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github+json"
    }

    response = requests.get(
        f"https://api.github.com/users/{username}/repos",
        headers=headers,
        params={"sort": "pushed", "per_page": 20}
    )

    if response.status_code != 200:
        return None

    repos = response.json()

    languages = Counter(r["language"] for r in repos if r.get("language"))

    topics = []
    for r in repos:
        topics.extend(r.get("topics", []))

    response = requests.get(
        f"https://api.github.com/users/{username}/events",
        headers=headers,
        params={"per_page": 10}
    )

    events = response.json() if response.status_code == 200 else []

    # event type breakdown — what kind of work they do
    event_types = Counter(e.get("type") for e in events)

    commit_hours = []
    for event in events:
        if event.get("type") == "PushEvent":
            created = event.get("created_at", "")
            try:
                dt = datetime.strptime(created, "%Y-%m-%dT%H:%M:%SZ")
                commit_hours.append(dt.hour)
            except ValueError:
                pass

    hour_dist = Counter(commit_hours)
    # label hours as morning/afternoon/night
    time_buckets = {
        "morning (6-12)": sum(hour_dist.get(h, 0) for h in range(6, 12)),
        "afternoon (12-18)": sum(hour_dist.get(h, 0) for h in range(12, 18)),
        "evening (18-24)": sum(hour_dist.get(h, 0) for h in range(18, 24)),
        "night (0-6)": sum(hour_dist.get(h, 0) for h in range(0, 6)),
    }

    return {
        "repos": [
            {
                "name": r["name"],
                "language": r.get("language"),
                "topics": r.get("topics", []),
                "stars": r.get("stargazers_count", 0),
                "is_fork": r.get("fork", False),
            }
            for r in repos
        ],
        "language_distribution": dict(languages.most_common(8)),
        "topics": list(set(topics)),
        "coding_time": time_buckets,
        "event_types": dict(event_types),
        "total_events": len(events),
    }


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


print(json.dumps(get_sleep_wake_data()))
