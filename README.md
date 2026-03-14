# Travel Itinerary Generator

Paste messy travel info — flight confirmations, hotel bookings, tour reservations, notes, anything — and get a clean, day-by-day itinerary in seconds.

## Features

- **Handles any input format** — paste from emails, booking sites, notes apps, all at once
- **Day-by-day timeline** with colour-coded event types (flights, hotels, trains, activities, etc.)
- **Save to browser** — itineraries persist in localStorage, accessible across sessions
- **Download for offline** — exports a self-contained HTML file that works without internet (great for airports)
- **Print-friendly** — the downloaded file prints cleanly

## Setup

**1. Get an Anthropic API key** from [console.anthropic.com](https://console.anthropic.com)

**2. Install dependencies**
```bash
pip install -r requirements.txt
```

**3. Configure your API key**
```bash
cp .env.example .env
# Edit .env and add your ANTHROPIC_API_KEY
```

**4. Run the server**
```bash
python app.py
```

**5. Open** [http://localhost:8000](http://localhost:8000)

## Usage

1. Paste any travel information into the text area (the messier the better — it can handle it)
2. Click **Generate Itinerary** or press `Ctrl+Enter`
3. Review your day-by-day plan
4. **Save** to browser storage for later, or **Download** as an offline HTML file

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
