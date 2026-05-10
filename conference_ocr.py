#!/usr/bin/env python3
"""
Conference Photo OCR

Reads a Trello board (one list per day, one card per talk with time in the name),
matches local conference photos to talks by EXIF timestamp, sends photos to Claude
Vision to extract slide text and key takeaways, and writes a structured markdown file.

Usage:
    python conference_ocr.py --photos-dir ./photos --output conference_notes.md

Environment variables (put in .env):
    ANTHROPIC_API_KEY   - Anthropic API key
    TRELLO_API_KEY      - Trello Power-Up API key
    TRELLO_TOKEN        - Trello user token
    TRELLO_BOARD_ID     - ID of the conference Trello board
"""

import base64
import datetime
import os
import re
import sys
from pathlib import Path
from typing import Optional

import anthropic
import click
import requests
from dotenv import load_dotenv
from PIL import Image, ExifTags

load_dotenv()

TRELLO_BASE = "https://api.trello.com/1"

# EXIF tag number for DateTimeOriginal
_EXIF_DATETIME_ORIGINAL = next(
    tag for tag, name in ExifTags.TAGS.items() if name == "DateTimeOriginal"
)

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}


# ---------------------------------------------------------------------------
# Trello
# ---------------------------------------------------------------------------

def _trello_params() -> dict:
    key = os.environ.get("TRELLO_API_KEY", "")
    token = os.environ.get("TRELLO_TOKEN", "")
    if not key or not token:
        click.echo(
            "ERROR: TRELLO_API_KEY and TRELLO_TOKEN must be set in your .env file.\n"
            "See .env.example for instructions.",
            err=True,
        )
        sys.exit(1)
    return {"key": key, "token": token}


def fetch_lists_with_cards(board_id: str) -> list[dict]:
    """Return all lists from the board, each with a 'cards' key."""
    params = _trello_params()
    resp = requests.get(f"{TRELLO_BASE}/boards/{board_id}/lists", params=params, timeout=15)
    resp.raise_for_status()
    lists = resp.json()

    for lst in lists:
        r = requests.get(f"{TRELLO_BASE}/lists/{lst['id']}/cards", params=params, timeout=15)
        r.raise_for_status()
        lst["cards"] = r.json()

    return lists


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------

_MONTH_MAP = {
    "january": 1, "february": 2, "march": 3, "april": 4,
    "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
    "jan": 1, "feb": 2, "mar": 3, "apr": 4,
    "jun": 6, "jul": 7, "aug": 8, "sep": 9,
    "oct": 10, "nov": 11, "dec": 12,
}

_WEEKDAY_MAP = {
    "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
    "friday": 4, "saturday": 5, "sunday": 6,
    "mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6,
}


def parse_date_from_list_name(name: str) -> Optional[datetime.date]:
    """
    Try to extract a calendar date from a Trello list name.

    Handles patterns like:
      "Day 1 – April 14"   "Tuesday 15th"   "April 14"   "14 April"
    Returns None if no date can be inferred.
    """
    lower = name.lower()
    today = datetime.date.today()
    year = today.year

    # Look for a month name + a nearby day number
    for month_str, month_num in _MONTH_MAP.items():
        if month_str in lower:
            day_match = re.search(r"\b(\d{1,2})\b", lower)
            if day_match:
                try:
                    return datetime.date(year, month_num, int(day_match.group(1)))
                except ValueError:
                    pass

    # Look for a weekday name and resolve to the nearest past occurrence
    for day_str, weekday in _WEEKDAY_MAP.items():
        if re.search(rf"\b{day_str}\b", lower):
            delta = (today.weekday() - weekday) % 7
            return today - datetime.timedelta(days=delta)

    return None


_TIME_RE = re.compile(
    r"\b(\d{1,2}):(\d{2})\s*(am|pm)?\b",
    re.IGNORECASE,
)


def parse_time_from_card_name(name: str) -> Optional[datetime.time]:
    """
    Extract a wall-clock time from a card name like:
      "9:00 - Opening Keynote"
      "14:30 Deep dive into…"
      "2:00 PM  Panel discussion"
    """
    m = _TIME_RE.search(name)
    if not m:
        return None

    hour, minute = int(m.group(1)), int(m.group(2))
    ampm = (m.group(3) or "").lower()

    if ampm == "pm" and hour != 12:
        hour += 12
    elif ampm == "am" and hour == 12:
        hour = 0

    try:
        return datetime.time(hour, minute)
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Schedule building
# ---------------------------------------------------------------------------

def build_schedule(lists: list[dict]) -> list[dict]:
    """
    Build a flat list of talk dicts, each with:
      list_name, day (date or None), card, start_time, end_time
    end_time = next talk's start_time, or start + 1 h for the last talk.
    """
    schedule = []

    for lst in lists:
        day = parse_date_from_list_name(lst["name"])

        timed = sorted(
            [(parse_time_from_card_name(c["name"]), c) for c in lst["cards"]],
            key=lambda x: x[0] or datetime.time(0, 0),
        )
        # Drop cards with no parseable time
        timed = [(t, c) for t, c in timed if t is not None]

        for i, (start, card) in enumerate(timed):
            if i + 1 < len(timed):
                end = timed[i + 1][0]
            else:
                end = (
                    datetime.datetime.combine(datetime.date.today(), start)
                    + datetime.timedelta(hours=1)
                ).time()

            schedule.append(
                {
                    "list_name": lst["name"],
                    "day": day,
                    "card": card,
                    "start": start,
                    "end": end,
                }
            )

    return schedule


# ---------------------------------------------------------------------------
# Photo scanning & matching
# ---------------------------------------------------------------------------

def photo_datetime(path: Path) -> Optional[datetime.datetime]:
    """Read DateTimeOriginal EXIF from an image. Returns None on any failure."""
    try:
        with Image.open(path) as img:
            exif = img._getexif()  # noqa: SLF001  (private but standard)
        if exif and _EXIF_DATETIME_ORIGINAL in exif:
            return datetime.datetime.strptime(
                exif[_EXIF_DATETIME_ORIGINAL], "%Y:%m:%d %H:%M:%S"
            )
    except Exception:
        pass
    return None


def scan_photos(directory: Path) -> list[tuple[Path, datetime.datetime]]:
    """Return (path, datetime) pairs for every image that has an EXIF timestamp."""
    results = []
    for path in sorted(directory.rglob("*")):
        if path.suffix.lower() not in IMAGE_EXTENSIONS:
            continue
        dt = photo_datetime(path)
        if dt:
            results.append((path, dt))
        else:
            click.echo(f"  [no EXIF] {path.name}", err=True)
    return results


def match_photos_to_schedule(
    photos: list[tuple[Path, datetime.datetime]],
    schedule: list[dict],
) -> tuple[dict[str, list[Path]], list[tuple[Path, datetime.datetime]]]:
    """
    Assign each photo to a talk slot by comparing date + time.

    If a talk's day is None (couldn't be parsed from the list name), matching
    falls back to time-only comparison — useful when lists are named "Day 1" etc.
    and the actual dates are unknown.

    Returns:
        matched   – card_id → [photo paths]
        unmatched – photos that fell outside every slot
    """
    matched: dict[str, list[Path]] = {slot["card"]["id"]: [] for slot in schedule}
    unmatched: list[tuple[Path, datetime.datetime]] = []

    for path, dt in photos:
        assigned = False
        for slot in schedule:
            if slot["day"] is not None and slot["day"] != dt.date():
                continue
            if slot["start"] <= dt.time() < slot["end"]:
                matched[slot["card"]["id"]].append(path)
                assigned = True
                break
        if not assigned:
            unmatched.append((path, dt))

    return matched, unmatched


# ---------------------------------------------------------------------------
# Claude Vision
# ---------------------------------------------------------------------------

_MEDIA_TYPES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".gif": "image/gif",
    ".webp": "image/webp",
}

_EXTRACTION_PROMPT = (
    "These are photographs of slides from a single conference talk. "
    "Please:\n"
    "1. Extract all readable text visible in the slides.\n"
    "2. Summarise the key points and takeaways as bullet points.\n\n"
    "Format your response exactly as:\n\n"
    "### Extracted Slide Text\n"
    "<text, one slide per paragraph>\n\n"
    "### Key Takeaways\n"
    "- <bullet>\n"
    "- <bullet>\n"
)


def extract_from_photos(client: anthropic.Anthropic, paths: list[Path]) -> str:
    content: list[dict] = []

    for path in paths:
        media_type = _MEDIA_TYPES.get(path.suffix.lower(), "image/jpeg")
        with open(path, "rb") as fh:
            data = base64.standard_b64encode(fh.read()).decode()
        content.append(
            {
                "type": "image",
                "source": {"type": "base64", "media_type": media_type, "data": data},
            }
        )

    content.append({"type": "text", "text": _EXTRACTION_PROMPT})

    response = client.messages.create(
        model="claude-opus-4-7",
        max_tokens=2048,
        messages=[{"role": "user", "content": content}],
    )
    return response.content[0].text


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

@click.command()
@click.option(
    "--photos-dir",
    required=True,
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    help="Directory containing conference photos (searched recursively).",
)
@click.option(
    "--output",
    default="conference_notes.md",
    show_default=True,
    help="Path for the output markdown file.",
)
@click.option(
    "--board-id",
    default=lambda: os.environ.get("TRELLO_BOARD_ID", ""),
    help="Trello board ID (overrides TRELLO_BOARD_ID env var).",
)
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="Show schedule and photo matches without calling Claude.",
)
def main(photos_dir: Path, output: str, board_id: str, dry_run: bool) -> None:
    """Extract text from conference slide photos and write organised notes."""

    if not board_id:
        click.echo(
            "ERROR: Provide --board-id or set TRELLO_BOARD_ID in .env.", err=True
        )
        sys.exit(1)

    # 1. Trello
    click.echo("Fetching Trello board…")
    lists = fetch_lists_with_cards(board_id)
    click.echo(f"  {len(lists)} lists, {sum(len(l['cards']) for l in lists)} cards total")

    schedule = build_schedule(lists)
    unparsed = sum(1 for l in lists for c in l["cards"]
                   if parse_time_from_card_name(c["name"]) is None)
    click.echo(f"  {len(schedule)} timed slots ({unparsed} cards skipped — no time found)")

    # 2. Photos
    click.echo(f"Scanning photos in {photos_dir}…")
    photos = scan_photos(photos_dir)
    click.echo(f"  {len(photos)} photos with EXIF timestamps")

    # 3. Match
    matched, unmatched = match_photos_to_schedule(photos, schedule)
    total_matched = sum(len(v) for v in matched.values())
    click.echo(
        f"  {total_matched} photos matched to talks, {len(unmatched)} unmatched"
    )

    if dry_run:
        click.echo("\n-- DRY RUN: talk schedule --")
        for slot in schedule:
            n = len(matched[slot["card"]["id"]])
            click.echo(
                f"  [{slot['list_name']}] {slot['start'].strftime('%H:%M')}–"
                f"{slot['end'].strftime('%H:%M')}  {slot['card']['name']}  ({n} photos)"
            )
        return

    # 4. OCR + write
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        click.echo("ERROR: ANTHROPIC_API_KEY not set.", err=True)
        sys.exit(1)
    client = anthropic.Anthropic(api_key=api_key)

    lines: list[str] = ["# Conference Notes\n"]
    current_list = None

    for slot in schedule:
        if slot["list_name"] != current_list:
            current_list = slot["list_name"]
            lines.append(f"\n## {current_list}\n")

        lines.append(f"\n### {slot['card']['name']}\n")

        card_photos = matched[slot["card"]["id"]]
        if not card_photos:
            lines.append("_No photos matched to this talk._\n")
            continue

        click.echo(
            f"  Processing '{slot['card']['name']}' "
            f"({len(card_photos)} photo{'s' if len(card_photos) != 1 else ''})…"
        )
        extracted = extract_from_photos(client, card_photos)
        lines.append(extracted)
        lines.append("\n")

    if unmatched:
        lines.append("\n---\n\n## Unmatched Photos\n")
        for path, dt in unmatched:
            lines.append(f"- `{path.name}` — taken {dt:%Y-%m-%d %H:%M}\n")

    output_path = Path(output)
    output_path.write_text("".join(lines), encoding="utf-8")
    click.echo(f"\nDone. Notes written to {output_path}")


if __name__ == "__main__":
    main()
