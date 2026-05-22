"""
collect API based behavioural data

Sources:
  - GitHub

Run separately from main.py:
    python collect_api.py your_name

Setup:
  GitHub  → create token at github.com/settings/tokens (read:user, repo)
            add GITHUB_TOKEN and GITHUB_USERNAME to .env
"""

import os
from datetime import datetime
from pathlib import Path
from collections import Counter
import requests
from dotenv import load_dotenv
import base64
# import spotipy
# from spotipy.oauth2 import SpotifyOAuth

load_dotenv()

TODAY = datetime.now().strftime("%Y-%m-%d")
DATA_DIR = Path.home() / ".cognitivetwin"
DATA_DIR.mkdir(exist_ok=True)


def step(label): print(f"\n  \033[94m→\033[0m  {label}")
def ok(label): print(f"  \033[92m✓\033[0m  {label}")
def skip(label): print(f"  \033[90m–\033[0m  {label}")
def warn(label): print(f"  \033[93m⚡\033[0m {label}")
def err(label): print(f"  \033[91m✗\033[0m  {label}")


def _github_get(path, token, params=None):
    response = requests.get(
        f"https://api.github.com{path}",
        headers={
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github+json"
        },
        params=params or {}
    )

    return response.json() if response.status_code == 200 else None


def _fetch_readme(owner, repo, token):
    data = _github_get(f"/repos/{owner}/{repo}/readme", token)

    if not data or "content" not in data:
        return None

    try:
        text = base64.b64decode(data["content"]).decode("utf-8", errors="ignore")
        clean = "\n".join(
            line for line in text.splitlines()
            if not line.startswith("#") or len(line) > 2
        )
        return clean[:200].strip()
    except Exception:
        return None


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

    repos = _github_get(f"/users/{username}/repos", token, params={"sort": "pushed", "per_page": 20})

    if not repos:
        return None

    languages = Counter(r["language"] for r in repos if r.get("language"))

    repo_summaries = []
    for r in repos[:5]:
        summary = {
            "name": r["name"],
            "language": r.get("language"),
            "description": r.get("description") or "",
            "stars": r.get("stargazers_count", 0),
            "is_fork": r.get("fork", False),
        }
        # fetch README if description is empty or very short
        if len(summary["description"]) < 20:
            readme = _fetch_readme(username, r["name"], token)
            if readme:
                summary["readme_excerpt"] = readme

        repo_summaries.append(summary)

    # remaining repos — just name + language (no README fetch, save API calls)
    for r in repos[5:]:
        repo_summaries.append({
            "name": r["name"],
            "language": r.get("language"),
            "is_fork": r.get("fork", False),
        })

    # recent events → commit hour distribution
    events = _github_get(f"/users/{username}/events", token, {"per_page": 100}) or []
    commit_hours = [
        datetime.strptime(e["created_at"], "%Y-%m-%dT%H:%M:%SZ").hour
        for e in events if e.get("type") == "PushEvent"
    ]
    hour_dist = Counter(commit_hours)
    time_buckets = {
        "morning (6-12)": sum(hour_dist.get(h, 0) for h in range(6, 12)),
        "afternoon (12-18)": sum(hour_dist.get(h, 0) for h in range(12, 18)),
        "evening (18-24)": sum(hour_dist.get(h, 0) for h in range(18, 24)),
        "night (0-6)": sum(hour_dist.get(h, 0) for h in range(0, 6)),
    }

    event_types = Counter(e.get("type") for e in events)

    return {
        "repos": repo_summaries,
        "language_distribution": dict(languages.most_common(8)),
        "coding_time": time_buckets,
        "event_types": dict(event_types),
    }
