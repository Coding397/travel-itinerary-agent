# Travel Itinerary Generator

Paste messy travel info — flight confirmations, hotel bookings, tour reservations, notes, anything — and get a clean, day-by-day itinerary in seconds.

Supports two backends: **Claude API** (paid, highest quality) or a **local model via Ollama** (free, runs on your machine).

## Features

- **Handles any input format** — paste from emails, booking sites, notes apps, all at once
- **Day-by-day timeline** with colour-coded event types (flights, hotels, trains, activities, etc.)
- **Save to browser** — itineraries persist in localStorage, accessible across sessions
- **Download for offline** — exports a self-contained HTML file that works without internet (great for airports)
- **Print-friendly** — the downloaded file prints cleanly

---

## Setup

**1. Install dependencies**
```bash
pip install -r requirements.txt
```

**2. Configure your backend** (choose one):

```bash
cp .env.example .env
```

Then edit `.env`.

---

### Option A — Claude API (paid, best quality)

Get an API key from [console.anthropic.com](https://console.anthropic.com), then set:
```
ANTHROPIC_API_KEY=sk-ant-...
```

---

### Option B — Local model via Ollama (free)

[Ollama](https://ollama.com) runs open-source LLMs locally. No API key, no cost, works offline.

**Install Ollama:**
```bash
# macOS
brew install ollama

# Linux
curl -fsSL https://ollama.com/install.sh | sh

# Windows: download installer from https://ollama.com
```

**Pull a model** (pick one based on your RAM):

| Model | RAM needed | Quality |
|-------|-----------|---------|
| `qwen2.5:7b` | ~5 GB | Good ⭐⭐⭐ (recommended) |
| `llama3.1:8b` | ~5 GB | Good ⭐⭐⭐ |
| `qwen2.5:14b` | ~9 GB | Better ⭐⭐⭐⭐ |
| `mistral:7b` | ~4 GB | Decent ⭐⭐ |

```bash
ollama pull qwen2.5:7b
```

**Set in `.env`:**
```
BACKEND=ollama
OLLAMA_MODEL=qwen2.5:7b
```

Ollama must be running when you use the app (`ollama serve` starts it if it isn't already).

---

**3. Run the server**
```bash
python app.py
```

**4. Open** [http://localhost:8000](http://localhost:8000)

The header shows which backend is active.

---

## Usage

1. Paste any travel information into the text area (the messier the better)
2. Click **Generate Itinerary** or press `Ctrl+Enter`
3. Review your day-by-day plan
4. **Save** to browser storage for later, or **Download** as an offline HTML file

---

## Supported event types

| Type | Examples |
|------|---------|
| ✈️ Flight | Departure & arrival, with flight numbers and terminals |
| 🏨 Hotel | Check-in and check-out, with addresses and booking refs |
| 🚂 Train | Rail journeys with times and booking references |
| 🚌 Bus / ⛴️ Ferry | Transfers and crossings |
| 🚗 Car rental | Pick-up and drop-off |
| 🎯 Activity / 🗺️ Tour | Sightseeing, guided tours, experiences |
| 🍽️ Restaurant | Dining reservations |
| 📋 Meeting | Business or personal meetings |

---

## Notes on local models

Local models are generally good at this task but less reliable than Claude at producing perfectly valid JSON on the first try. If you get a parse error, just hit Generate again — the result is often fine on a second attempt. `qwen2.5` models tend to be the most reliable at following structured output instructions.
