#!/usr/bin/env python3
"""Runs hourly inside a morning/evening window (via GitHub Actions cron).
Uses a probability roll so the exact moment inside the window is randomized
(spacing-effect psychology: unpredictable timing beats a fixed daily alarm).
State (whether today's window already fired) is committed back to the repo
so it persists across ephemeral runner instances."""
import json
import os
import random
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
            return name, start, end
    return None, None, None

def should_fire(window_name, start, end, hour, state, today_str):
    if state.get(window_name) == today_str:
        return False
    hours_left = end - hour + 1
    return random.random() < (1.0 / hours_left)

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

    window_name, start, end = current_window(hour)
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
    if not force and not should_fire(window_name, start, end, hour, state, today_str):
        print(f"Rolled no-fire for {window_name} (hour={hour})")
        return

    send_ntfy(topic, "English · review time", "Tap to review your due words", APP_URL)

    state[window_name] = today_str
    save_state(state)
    print(f"Reminder sent for window={window_name}")

if __name__ == "__main__":
    main()
