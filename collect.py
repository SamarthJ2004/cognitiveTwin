"""
collect behavioural data (MacOS only)

Brave History
Bash History
Zsh History
App Usage

Run separately from main.py:
    python collect.py your_name
"""

import json
import os
import sys
from urllib.parse import urlparse, parse_qs
from datetime import datetime, timedelta
from pathlib import Path
import sqlite3
import shutil
import re
from openai import OpenAI
import db

TODAY = datetime.now().strftime("%Y-%m-%d")

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


def get_brave_history(days=7, limit=200):
    # for Default Profile only
    src = Path.home() / "Library/Application Support/BraveSoftware/Brave-Browser/Default/History"

    if not src.exists():
        return []

    # Chrome/Brave store time as: microseconds since 1601-01-01 00:00:00 UTC
    chrome_epoch = datetime(1601, 1, 1)

    since = datetime.now() - timedelta(days=days)
    since_chrome = int((since-chrome_epoch).total_seconds() * 1_000_000)

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
    return [r[0] for r in rows if r[0]]


def _sanitize_command(cmd):
    # to remove api keys, passwords and sensitive data from the terminal history
    lower = cmd.lower()

    for pattern in SENSITIVE_PATTERNS:
        if re.search(pattern, lower, re.IGNORECASE):
            return "[REDACTED SENSITIVE COMMAND]"

    # Hide long suspicious strings
    cmd = re.sub(r'([A-Za-z0-9_\-]{24,})', '[REDACTED]', cmd)

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
        return [{"app": r[0], "minutes": int(r[1])} for r in rows if (int(r[1]) > 5)]
    except Exception as e:
        print("Error: ", e)
        return []


def get_running_apps():
    return


def get_apple_music_taste():
    return


def analyze_behavioral_data(data_summary, stated_profile_text):
    ai = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    prompt = f"""
    You are analyzing someone's real digital behavior to build the behavioral layer of their cognitive profile.

Their STATED profile (what they say about themselves):
{stated_profile_text}

Their BEHAVIORAL data (what they actually do):
{json.dumps(data_summary, indent=2)}

Extract cognitive signals. Return ONLY a JSON object:
{{
  "beliefs": [
    {{
      "text": "a belief that their BEHAVIOR reveals — not what they said, what they DO implies",
      "confidence": 0.0-1.0
    }}
  ],
  "patterns": [
    "a specific recurring behavioral pattern visible in the data — be precise, not generic"
  ],
  "topics": [
    "specific topics they actually spend time on — prefer precise over broad"
  ],
  "contradictions": [
    {{
      "text": "describe a specific conflict between their stated profile and their actual behavior",
      "self_a": "stated",
      "self_b": "behavioral",
      "confidence": 0.0-1.0
    }}
  ],
  "summary": "2 sentences — what does this person ACTUALLY do vs what they say they do?"
}}

Rules:
- behavioral beliefs come from patterns of action, not their words
- be specific: not 'uses social media a lot' but 'spends significant time on video content despite claiming to prefer reading'
- contradictions only if genuinely present — compare against the stated profile above
- Return ONLY valid JSON, no markdown"""

    response = ai.chat.completions.create(
        model="gpt-4o-mini",
        max_tokens=1200,
        messages=[{"role": "user", "content": prompt}]
    )

    text = response.choices[0].message.content.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    return json.loads(text.strip())


def store_behavioral_signals(session, user_id, signals):
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

    print(data_summary)

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
            signals = analyze_behavioral_data(data_summary, stated_text)
        except Exception as e:
            err(f"Analysis failed: {e}")
            return

        step("Storing to graph...")
        store_behavioral_signals(session, user_id, signals)
        ok("Behavioral layer updated")

    print(f"\n\033[93mBehavioral summary:\033[0m")
    print(f"  {signals.get('summary', '')}")

    contradictions = signals.get("contradictions", [])
    if contradictions:
        print(f"\n\033[91mContradictions with your stated self:\033[0m")
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
