#!/usr/bin/env python3
"""Runs every 15min during waking hours (via GitHub Actions cron).

Design notes (v3):
- GitHub silently delays/drops a chunk of scheduled cron triggers under load.
  A run can land 30-90min late, so the two daily windows must NOT have a gap
  between them -- otherwise a late run lands in the dead zone and gets
  skipped, which is what silently broke morning delivery in v2.
- For spacing-effect randomness without sacrificing reliability: the first
  run that sees a given window "today" picks a random target minute inside
  that window and stores it in state. Every later run in that window just
  checks "have we passed the target yet" -- so delivery still lands at an
  unpredictable moment, but any run after the target (not just the first)
  can be the one that actually sends.
State is committed back to the repo so it persists across ephemeral runners.
"""
import json
import os
import random
import subprocess
import sys
from datetime import datetime, timezone, timedelta

STATE_FILE = "state.json"
APP_URL = "https://claude.ai/artifact/QPvmQ8UxcExJQBSN7q6yCb"
MSK = timezone(timedelta(hours=3))

# Windows in Moscow local time -- back-to-back, no gap, so a delayed run
# always lands in exactly one of them.
WINDOWS = {
    "morning": (7, 14),   # 07:00 - 14:00
    "evening": (14, 23),  # 14:00 - 23:00
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
        if start <= hour < end:
            return name, start, end
    return None, None, None

def minutes_since_midnight(dt):
    return dt.hour * 60 + dt.minute

def get_or_pick_target(state, window_name, start, end, today_str):
    key = f"{window_name}_target"
    entry = state.get(key)
    if entry and entry.get("date") == today_str:
        return entry["minute"]
    target_minute = random.randint(start * 60, end * 60 - 1)
    state[key] = {"date": today_str, "minute": target_minute}
    return target_minute

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

    topic = os.environ.get("NTFY_TOPIC")
    if not topic:
        print("NTFY_TOPIC secret not set", file=sys.stderr)
        sys.exit(1)

    state = load_state()

    if force:
        send_ntfy(topic, "English · review time", "Tap to review your due words", APP_URL)
        print("Reminder sent (forced)")
        return

    if state.get(window_name) == today_str:
        print(f"Already sent {window_name} today")
        return

    target_minute = get_or_pick_target(state, window_name, start, end, today_str)
    now_minute = minutes_since_midnight(now)

    if now_minute < target_minute:
        save_state(state)  # persist the freshly-picked target
        print(f"Target for {window_name} is {target_minute//60:02d}:{target_minute%60:02d} MSK, not there yet")
        return

    send_ntfy(topic, "English · review time", "Tap to review your due words", APP_URL)
    state[window_name] = today_str
    save_state(state)
    print(f"Reminder sent for window={window_name} (target was {target_minute//60:02d}:{target_minute%60:02d})")

if __name__ == "__main__":
    main()
