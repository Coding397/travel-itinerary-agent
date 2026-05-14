#!/usr/bin/env python3
"""Exports a Trello board to a markdown file. One ## per list, one entry per card."""

import os, sys, requests
from dotenv import load_dotenv

load_dotenv()

KEY   = os.environ.get("TRELLO_API_KEY", "")
TOKEN = os.environ.get("TRELLO_TOKEN", "")
BOARD = os.environ.get("TRELLO_BOARD_ID", "")

if not all([KEY, TOKEN, BOARD]):
    sys.exit("Set TRELLO_API_KEY, TRELLO_TOKEN, and TRELLO_BOARD_ID in .env")

BASE   = "https://api.trello.com/1"
PARAMS = {"key": KEY, "token": TOKEN}


def get(path):
    r = requests.get(f"{BASE}{path}", params=PARAMS, timeout=15)
    r.raise_for_status()
    return r.json()


lists = get(f"/boards/{BOARD}/lists")
lines = ["# Conference Notes\n"]

for lst in lists:
    lines.append(f"\n## {lst['name']}\n")
    for card in get(f"/lists/{lst['id']}/cards"):
        lines.append(f"\n### {card['name']}\n")
        if card.get("desc"):
            lines.append(card["desc"] + "\n")

output = "conference_notes.md"
with open(output, "w") as f:
    f.write("\n".join(lines))
print(f"Written to {output}")
