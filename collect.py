"""
collect behavioural data (MacOS only)

Brave History
Bash History
Zsh History
App Usage

Run separately from main.py:
    python collect.py your_name
"""

from urllib.parse import urlparse, parse_qs, unquote_plus
from datetime import datetime, timedelta
from pathlib import Path
import sqlite3
import shutil
import re

TODAY = datetime.now().strftime("&Y-%m-%d")

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
        return [{"app": r[0], "minutes": int(r[1])} for r in rows if int(r[1])]
    except Exception as e:
        print("Error: ", e)
        return []


def get_running_apps():
    return


def get_apple_music_taste():
    return
