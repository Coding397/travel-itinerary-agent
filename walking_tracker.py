import os
import sqlite3
import io
from datetime import date, timedelta, datetime
from pathlib import Path

from flask import Flask, request, redirect, url_for, render_template, send_file, flash
from PIL import Image, ImageDraw, ImageFont
from werkzeug.utils import secure_filename

BASE_DIR = Path(__file__).parent
DB_PATH = BASE_DIR / "walks.db"
UPLOAD_DIR = BASE_DIR / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png", "gif", "webp", "heic"}

app = Flask(__name__)
app.secret_key = "walking-tracker-secret"
app.config["MAX_CONTENT_LENGTH"] = 20 * 1024 * 1024  # 20 MB


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS walks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                walk_date TEXT NOT NULL,
                km REAL NOT NULL,
                location TEXT NOT NULL,
                notes TEXT,
                photo_path TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            )
        """)
        conn.commit()


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    with get_db() as conn:
        walks = conn.execute(
            "SELECT * FROM walks ORDER BY walk_date DESC, created_at DESC"
        ).fetchall()
    today = date.today().isoformat()
    return render_template("index.html", walks=walks, today=today)


@app.route("/log", methods=["POST"])
def log_walk():
    walk_date = request.form.get("walk_date") or date.today().isoformat()
    km_str = request.form.get("km", "0").strip()
    location = request.form.get("location", "").strip()
    notes = request.form.get("notes", "").strip()

    try:
        km = float(km_str)
    except ValueError:
        flash("Please enter a valid number for kilometres.")
        return redirect(url_for("index"))

    if not location:
        flash("Please enter where you walked.")
        return redirect(url_for("index"))

    photo_path = None
    file = request.files.get("photo")
    if file and file.filename and allowed_file(file.filename):
        filename = f"{walk_date}_{secure_filename(file.filename)}"
        dest = UPLOAD_DIR / filename
        # Avoid overwriting: append a counter if necessary
        counter = 1
        while dest.exists():
            stem = f"{walk_date}_{counter}_{secure_filename(file.filename)}"
            dest = UPLOAD_DIR / stem
            counter += 1
        file.save(dest)
        photo_path = dest.name

    with get_db() as conn:
        conn.execute(
            "INSERT INTO walks (walk_date, km, location, notes, photo_path) VALUES (?,?,?,?,?)",
            (walk_date, km, location, notes, photo_path),
        )
        conn.commit()

    flash(f"Walk logged: {km:.2f} km at {location}!")
    return redirect(url_for("index"))


@app.route("/delete/<int:walk_id>", methods=["POST"])
def delete_walk(walk_id):
    with get_db() as conn:
        row = conn.execute("SELECT photo_path FROM walks WHERE id=?", (walk_id,)).fetchone()
        if row and row["photo_path"]:
            photo = UPLOAD_DIR / row["photo_path"]
            if photo.exists():
                photo.unlink()
        conn.execute("DELETE FROM walks WHERE id=?", (walk_id,))
        conn.commit()
    flash("Walk deleted.")
    return redirect(url_for("index"))


@app.route("/photo/<path:filename>")
def serve_photo(filename):
    path = UPLOAD_DIR / filename
    if not path.exists():
        return "Not found", 404
    return send_file(path)


@app.route("/collage")
def collage():
    cutoff = (date.today() - timedelta(days=30)).isoformat()
    with get_db() as conn:
        walks = conn.execute(
            "SELECT * FROM walks WHERE walk_date >= ? ORDER BY walk_date ASC",
            (cutoff,),
        ).fetchall()

    img_bytes = build_collage(walks)
    return send_file(img_bytes, mimetype="image/png", download_name="walking_collage.png")


# ---------------------------------------------------------------------------
# Collage builder
# ---------------------------------------------------------------------------

CELL_W, CELL_H = 300, 320
THUMB_H = 240
COLS = 5
PAD = 16
HEADER_H = 90
FONT_SIZE_DATE = 16
FONT_SIZE_KM = 22
FONT_SIZE_LOC = 14
BG_COLOR = (245, 240, 230)
CARD_COLOR = (255, 255, 255)
ACCENT = (255, 107, 53)   # warm orange
TEXT_DARK = (40, 40, 40)
TEXT_MUTED = (120, 110, 100)


def _load_font(size):
    """Try to load a system font, fall back to default."""
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "C:/Windows/Fonts/arial.ttf",
    ]
    for path in candidates:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                pass
    return ImageFont.load_default()


def _load_font_regular(size):
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/usr/share/fonts/TTF/DejaVuSans.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "C:/Windows/Fonts/arial.ttf",
    ]
    for path in candidates:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                pass
    return ImageFont.load_default()


def _thumbnail(photo_path: str, width: int, height: int) -> Image.Image:
    """Load & crop-to-fill a photo, or return a placeholder."""
    img_path = UPLOAD_DIR / photo_path
    if img_path.exists():
        try:
            img = Image.open(img_path).convert("RGB")
            # Crop to aspect ratio
            aspect = width / height
            iw, ih = img.size
            if iw / ih > aspect:
                new_w = int(ih * aspect)
                offset = (iw - new_w) // 2
                img = img.crop((offset, 0, offset + new_w, ih))
            else:
                new_h = int(iw / aspect)
                offset = (ih - new_h) // 2
                img = img.crop((0, offset, iw, offset + new_h))
            img = img.resize((width, height), Image.LANCZOS)
            return img
        except Exception:
            pass
    # Placeholder gradient
    placeholder = Image.new("RGB", (width, height), (200, 195, 185))
    draw = ImageDraw.Draw(placeholder)
    draw.text((width // 2 - 20, height // 2 - 10), "No photo", fill=(150, 145, 135))
    return placeholder


def _draw_rounded_rect(draw, xy, radius, fill):
    x0, y0, x1, y1 = xy
    draw.rectangle([x0 + radius, y0, x1 - radius, y1], fill=fill)
    draw.rectangle([x0, y0 + radius, x1, y1 - radius], fill=fill)
    draw.ellipse([x0, y0, x0 + 2 * radius, y0 + 2 * radius], fill=fill)
    draw.ellipse([x1 - 2 * radius, y0, x1, y0 + 2 * radius], fill=fill)
    draw.ellipse([x0, y1 - 2 * radius, x0 + 2 * radius, y1], fill=fill)
    draw.ellipse([x1 - 2 * radius, y1 - 2 * radius, x1, y1], fill=fill)


def build_collage(walks) -> io.BytesIO:
    walks = list(walks)
    n = len(walks)

    if n == 0:
        # Return a simple "no data" image
        img = Image.new("RGB", (800, 400), BG_COLOR)
        draw = ImageDraw.Draw(img)
        font = _load_font(36)
        draw.text((80, 160), "No walks logged in the past 30 days!", fill=ACCENT, font=font)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)
        return buf

    rows = (n + COLS - 1) // COLS
    canvas_w = COLS * (CELL_W + PAD) + PAD
    canvas_h = HEADER_H + rows * (CELL_H + PAD) + PAD + 60  # 60 for footer stats

    canvas = Image.new("RGB", (canvas_w, canvas_h), BG_COLOR)
    draw = ImageDraw.Draw(canvas)

    # Header
    font_title = _load_font(36)
    font_sub = _load_font_regular(18)
    total_km = sum(float(w["km"]) for w in walks)
    draw.rectangle([0, 0, canvas_w, HEADER_H], fill=ACCENT)
    draw.text((PAD + 6, 14), "My Walking Journal", fill=(255, 255, 255), font=font_title)
    date_range = f"Past 30 days  •  {n} walk{'s' if n != 1 else ''}  •  {total_km:.1f} km total"
    draw.text((PAD + 8, 58), date_range, fill=(255, 220, 200), font=font_sub)

    font_date = _load_font(FONT_SIZE_DATE)
    font_km = _load_font(FONT_SIZE_KM)
    font_loc = _load_font_regular(FONT_SIZE_LOC)

    for i, walk in enumerate(walks):
        col = i % COLS
        row = i // COLS
        x = PAD + col * (CELL_W + PAD)
        y = HEADER_H + PAD + row * (CELL_H + PAD)

        # Card background
        _draw_rounded_rect(draw, (x, y, x + CELL_W, y + CELL_H), radius=10, fill=CARD_COLOR)

        # Photo
        thumb = _thumbnail(walk["photo_path"] or "", CELL_W - 4, THUMB_H - 4)
        canvas.paste(thumb, (x + 2, y + 2))

        # Accent stripe under photo
        draw.rectangle([x, y + THUMB_H, x + CELL_W, y + THUMB_H + 4], fill=ACCENT)

        text_y = y + THUMB_H + 8

        # Date
        try:
            d = datetime.strptime(walk["walk_date"], "%Y-%m-%d")
            date_str = d.strftime("%b %-d, %Y")
        except Exception:
            date_str = walk["walk_date"]
        draw.text((x + 8, text_y), date_str, fill=TEXT_MUTED, font=font_date)
        text_y += 20

        # KM
        km_str = f"{float(walk['km']):.2f} km"
        draw.text((x + 8, text_y), km_str, fill=ACCENT, font=font_km)
        text_y += 28

        # Location (truncate if long)
        loc = walk["location"]
        if len(loc) > 28:
            loc = loc[:25] + "..."
        draw.text((x + 8, text_y), loc, fill=TEXT_DARK, font=font_loc)

    # Footer stats bar
    fy = canvas_h - 55
    draw.rectangle([0, fy, canvas_w, canvas_h], fill=(230, 220, 210))
    font_footer = _load_font_regular(16)
    avg_km = total_km / n if n else 0
    best = max(walks, key=lambda w: float(w["km"]))
    footer = (
        f"Average: {avg_km:.2f} km/walk   •   "
        f"Best day: {float(best['km']):.2f} km ({best['location']})   •   "
        f"Generated {date.today().strftime('%B %-d, %Y')}"
    )
    draw.text((PAD, fy + 18), footer, fill=TEXT_MUTED, font=font_footer)

    buf = io.BytesIO()
    canvas.save(buf, format="PNG")
    buf.seek(0)
    return buf


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    init_db()
    app.run(debug=True, port=5050)
