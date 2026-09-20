#!/usr/bin/env python3
"""Runs every 15min inside a morning/evening window (via GitHub Actions cron).
GitHub silently drops a chunk of scheduled cron triggers under load, so a
probability roll on top of that made delivery too unreliable -- fires as soon
as the window opens and GH actually executes a run (that itself lands at an
unpredictable minute, which is enough randomness for the spacing effect).
State (whether today's window already fired) is committed back to the repo
so it persists across ephemeral runner instances."""
import json
import os
import subprocess
import sys
from datetime import datetime, timezone, timedelta

STATE_FILE = "state.json"
APP_URL = "https://claude.ai/artifact/QPvmQ8UxcExJQBSN7q6yCb"
MSK = timezone(timedelta(hours=3))

# Windows in Moscow local time
WINDOWS = {
    "morning": (9, 13),
    "evening": (17, 22),
}

def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            return json.load(f)
    return {}

def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)

def current_window(hour):
    for name, (start, end) in WINDOWS.items():
        if start <= hour <= end:
            return name
    return None

def should_fire(window_name, state, today_str):
    return state.get(window_name) != today_str

def send_ntfy(topic, title, body, click_url):
    r = subprocess.run(
        ["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}",
         "-d", body, f"https://ntfy.sh/{topic}",
         "-H", f"Title: {title}", "-H", "Priority: default",
         "-H", "Tags: books", "-H", f"Click: {click_url}"],
        check=False, capture_output=True, text=True,
    )
    print(f"ntfy status: {r.stdout}", file=sys.stderr)

def main():
    now = datetime.now(MSK)
    today_str = now.date().isoformat()
    hour = now.hour

    force = os.environ.get("FORCE_FIRE") == "1"

    window_name = current_window(hour)
    if window_name is None and not force:
        print(f"Outside any window (MSK hour={hour}), skipping")
        return

    if force:
        window_name = window_name or "manual"

    topic = os.environ.get("NTFY_TOPIC")
    if not topic:
        print("NTFY_TOPIC secret not set", file=sys.stderr)
        sys.exit(1)

    state = load_state()
    if not force and not should_fire(window_name, state, today_str):
        print(f"Already sent {window_name} today")
        return

    send_ntfy(topic, "English · review time", "Tap to review your due words", APP_URL)

    state[window_name] = today_str
    save_state(state)
    print(f"Reminder sent for window={window_name}")

if __name__ == "__main__":
    main()
