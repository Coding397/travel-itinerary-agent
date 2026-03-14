from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import StreamingResponse, FileResponse, JSONResponse
from anthropic import AsyncAnthropic
import json
import os
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(title="Travel Itinerary Generator")

SYSTEM_PROMPT = """You are an expert travel itinerary parser. Parse the user's travel information (which may be messy, from multiple sources, poorly formatted) and return a clean, structured JSON itinerary.

The input may include: email confirmations, hotel bookings, flight details, tour bookings, notes, or any mix of formats and sources.

Return ONLY a valid JSON object (no markdown, no code blocks, no explanation) in exactly this format:

{
  "trip_name": "Descriptive trip name",
  "start_date": "YYYY-MM-DD",
  "end_date": "YYYY-MM-DD",
  "days": [
    {
      "date": "YYYY-MM-DD",
      "day_number": 1,
      "location": "Primary city, Country",
      "summary": "One-line summary of the day",
      "events": [
        {
          "time": "HH:MM or null",
          "end_time": "HH:MM or null",
          "type": "flight|hotel_checkin|hotel_checkout|train|bus|ferry|car_rental|car_return|activity|tour|restaurant|meeting|other",
          "title": "Short descriptive title",
          "details": "Full details: flight numbers, airline, terminal, hotel name/address, operator, booking info, etc.",
          "confirmation": "Booking reference/confirmation number or null",
          "notes": "Important reminders, tips, or warnings"
        }
      ]
    }
  ],
  "important_notes": ["Trip-wide notes: visa requirements, currency, health advisories, etc."]
}

Rules:
1. Include EVERY day from start_date to end_date, including pure transit/travel days
2. For flights: add departure event on departure day; if overnight flight, add arrival event on arrival day
3. For hotels: add hotel_checkin event on first night, hotel_checkout on departure day
4. Sort events within each day by time (null times go last)
5. If a time is genuinely unknown, use null — do not guess
6. "location" = the primary place the traveler is based that day (destination city, not just passing through)
7. Be thorough — include every booking reference, address, and useful detail you can find
8. Return ONLY the JSON object. Nothing else."""


@app.get("/")
async def root():
    return FileResponse("static/index.html")


@app.post("/api/generate")
async def generate_itinerary(request: Request):
    body = await request.json()
    text = body.get("text", "").strip()

    if not text:
        return JSONResponse({"error": "No travel information provided"}, status_code=400)

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        return JSONResponse(
            {"error": "ANTHROPIC_API_KEY is not configured on the server"},
            status_code=500,
        )

    client = AsyncAnthropic(api_key=api_key)

    async def event_stream():
        try:
            yield f"data: {json.dumps({'type': 'status', 'message': 'Analyzing your travel information...'})}\n\n"

            collected = []
            async with client.messages.stream(
                model="claude-opus-4-6",
                max_tokens=16000,
                thinking={"type": "adaptive"},
                system=SYSTEM_PROMPT,
                messages=[
                    {
                        "role": "user",
                        "content": f"Parse this travel information into a structured itinerary:\n\n{text}",
                    }
                ],
            ) as stream:
                yield f"data: {json.dumps({'type': 'status', 'message': 'Building your itinerary...'})}\n\n"
                async for chunk in stream.text_stream:
                    collected.append(chunk)

            raw = "".join(collected).strip()

            # Strip markdown code fences if present
            if raw.startswith("```"):
                lines = raw.splitlines()
                if lines[0].startswith("```"):
                    lines = lines[1:]
                if lines and lines[-1].strip() == "```":
                    lines = lines[:-1]
                raw = "\n".join(lines).strip()

            # Extract JSON object
            start = raw.find("{")
            end = raw.rfind("}") + 1
            if start == -1 or end <= start:
                yield f"data: {json.dumps({'type': 'error', 'message': 'Could not extract itinerary data. Please include more travel details and try again.'})}\n\n"
                return

            itinerary = json.loads(raw[start:end])
            yield f"data: {json.dumps({'type': 'complete', 'data': itinerary})}\n\n"

        except json.JSONDecodeError:
            yield f"data: {json.dumps({'type': 'error', 'message': 'Failed to parse the response as JSON. Please try again.'})}\n\n"
        except Exception as e:
            msg = str(e)
            if "authentication" in msg.lower() or "api_key" in msg.lower():
                msg = "Invalid API key. Please check your ANTHROPIC_API_KEY."
            elif "rate_limit" in msg.lower():
                msg = "Rate limit reached. Please wait a moment and try again."
            yield f"data: {json.dumps({'type': 'error', 'message': msg})}\n\n"
        finally:
            yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


app.mount("/static", StaticFiles(directory="static"), name="static")

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)
