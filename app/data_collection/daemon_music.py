"""
daemon_music.py — macOS Music Behavior Tracker

Tracks:
- Spotify
- Apple Music

Collects:
- track changes
- listening sessions
- genre patterns
- skip behavior
- listening habits

Data saved to:
    ~/.cognitivetwin/music.json
"""

import json
import signal
import subprocess
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

DATA_DIR = Path.home() / ".cognitivetwin"
DATA_DIR.mkdir(exist_ok=True)
OUTPUT = DATA_DIR / "music.json"

POLL_INTERVAL = 5
SAVE_INTERVAL = 120
MIN_LISTEN_SECS = 15

state = {
    "current": None,
    "track_start": None,
    "sessions": [],
    "hourly_counts": defaultdict(int),
}


TRACK_SCRIPT = '''
    if player state is playing then

        set t to current track

        try
            set trackName to name of t
        on error
            set trackName to ""
        end try

        try
            set trackArtist to artist of t
        on error
            set trackArtist to ""
        end try

        try
            set trackAlbum to album of t
        on error
            set trackAlbum to ""
        end try

        try
            set trackGenre to genre of t
        on error
            set trackGenre to ""
        end try

        try
            set trackDuration to duration of t
        on error
            set trackDuration to 0
        end try

        try
            set trackPosition to player position
        on error
            set trackPosition to 0
        end try

        try
            set trackYear to year of t
        on error
            set trackYear to ""
        end try

        try
            set trackPlayedCount to played count of t
        on error
            set trackPlayedCount to 0
        end try

        return "name: " & trackName & linefeed & ¬
            "artist: " & trackArtist & linefeed & ¬
            "album: " & trackAlbum & linefeed & ¬
            "genre: " & trackGenre & linefeed & ¬
            "duration: " & trackDuration & linefeed & ¬
            "position: " & trackPosition & linefeed & ¬
            "year:" & trackYear & linefeed & ¬
            "played_count: " & trackPlayedCount

    end if
'''

SPOTIFY_SCRIPT = f'''
tell application "Spotify"
{TRACK_SCRIPT}
end tell
return ""
'''

APPLE_MUSIC_SCRIPT = f'''
tell application "Music"
{TRACK_SCRIPT}
end tell
return ""
'''


def _run_script(script):
    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True, text=True, timeout=3
        )
        return result.stdout.strip()
    except Exception:
        return ""


def parse_metadata(raw):
    data = {}

    for line in raw.splitlines():
        if ":" not in line:
            continue

        key, value = line.split(":", 1)
        data[key.strip()] = value.strip()

    numeric_fields = [
        "duration",
        "position",
        "year",
        "played_count",
    ]

    for field in numeric_fields:
        if field in data:
            try:
                data[field] = float(data[field])
            except Exception:
                pass

    return data


def get_now_playing():
    # Spotify
    out = _run_script(SPOTIFY_SCRIPT)
    if out:
        parsed = parse_metadata(out)
        if parsed:
            parsed["source"] = "spotify"
            # spotify duration is milliseconds
            if "duration" in parsed:
                parsed["duration"] /= 1000
            return parsed

    # Apple Music
    out = _run_script(APPLE_MUSIC_SCRIPT)
    if out:
        parsed = parse_metadata(out)
        if parsed:
            parsed["source"] = "apple_music"
            return parsed

    return None


def _close_current_session():
    current = state["current"]

    if not current or not state["track_start"]:
        return

    duration = time.time() - state["track_start"]

    if duration < MIN_LISTEN_SECS:
        return

    hour = datetime.fromtimestamp(state["track_start"]).hour

    session = {
        "track": current.get("name"),
        "artist": current.get("artist"),
        "album": current.get("album"),
        "genre": current.get("genre"),
        "source": current.get("source"),
        "duration_s": round(duration),
        "track_duration_s": current.get("duration"),
        "completion_ratio": round(min(duration / current.get("duration", duration), 1.0), 2,) if current.get("duration") else None,
        "hour": hour,
        "date": datetime.fromtimestamp(
            state["track_start"]
        ).strftime("%Y-%m-%d"),
    }

    state["sessions"].append(session)
    state["hourly_counts"][hour] += 1

    print(
        f"  \033[90m{datetime.now().strftime('%H:%M:%S')}\033[0m"
        f"  ✓ {current.get('name')} ({duration:.0f}s)"
    )


def on_track_change(new_track):
    _close_current_session()

    state["current"] = new_track
    state["track_start"] = time.time()

    if new_track:
        print(
            f"  \033[94m♪\033[0m "
            f"{new_track.get('name')} "
            f"— {new_track.get('artist')} "
            f"[{new_track.get('source')}]"
        )


def _classify_listening(skip_rate, total_minutes, artist_counts,):
    signals = []

    if skip_rate > 0.4:
        signals.append("high skip rate — exploratory or unsettled")
    elif skip_rate < 0.1:
        signals.append("low skip rate — focused or comfort listening")

    unique_artists = len(artist_counts)

    if unique_artists <= 2:
        signals.append("low artist variety — deep focus pattern")
    elif unique_artists >= 8:
        signals.append("high variety — exploratory listening")

    if total_minutes > 120:
        signals.append("heavy listening — music central to regulation today")

    return signals or ["no strong signal"]


def save():
    sessions = state["sessions"]

    if not sessions and not state["current"]:
        return

    artist_counts = Counter(s["artist"] for s in sessions if s.get("artist"))

    skips = sum(1 for s in sessions if s["duration_s"] < 60)

    skip_rate = round(skips / len(sessions), 2,)

    total_minutes = sum(s["duration_s"] for s in sessions) / 60

    summary = {
        "sessions_today": len(sessions),
        "total_minutes": round(total_minutes, 1),
        "top_artists": dict(artist_counts.most_common(10)),
        "skip_rate": skip_rate,
        "listening_by_hour": dict(state["hourly_counts"]),
        "recent_tracks": sessions[-30:],
        "listening_style": _classify_listening(
            skip_rate,
            total_minutes,
            artist_counts,
        ),
        "last_updated": datetime.now().isoformat(),

        "currently_playing": state["current"],
        "current_session_seconds": (
            round(time.time() - state["track_start"])
            if state["track_start"]
            else 0
        ),
    }

    OUTPUT.write_text(json.dumps(summary, indent=2))

    return summary


def shutdown(sig, frame):
    print("\nSaving...")
    _close_current_session()
    summary = save()

    if summary:
        print(f"{summary['sessions_today']} tracks\n · {summary['total_minutes']} min")
        print(f"Style: {summary['listening_style']}")

    sys.exit(0)


def main():
    print("\n\033[94mMusic Tracker\033[0m")
    print(f"Output: {OUTPUT}")
    print("Tracking Spotify + Apple Music")
    print("Press Ctrl+C to stop.\n")

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    last_save = time.time()

    previous_signature = None

    while True:
        current = get_now_playing()
        if current:
            signature = (
                current.get("name"),
                current.get("artist"),
                current.get("album"),
                current.get("source"),
            )

            if signature != previous_signature:
                on_track_change(current)
                previous_signature = signature

        else:
            # playback stopped
            if previous_signature is not None:
                _close_current_session()

                state["current"] = None
                state["track_start"] = None
                previous_signature = None

        if time.time() - last_save >= SAVE_INTERVAL:
            save()
            last_save = time.time()

        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
