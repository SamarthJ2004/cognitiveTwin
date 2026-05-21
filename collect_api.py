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
from datetime import datetime
from pathlib import Path
from collections import Counter
import requests
from dotenv import load_dotenv
from openai import OpenAI

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
