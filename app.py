from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import StreamingResponse, FileResponse, JSONResponse
import json
import os
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(title="Travel Itinerary Generator")

# ── Backend selection ─────────────────────────────────────────────────────────
# Set BACKEND=ollama in .env to use a local model via Ollama (free).
# Leave unset or set BACKEND=anthropic to use Claude (paid).
BACKEND = os.getenv("BACKEND", "anthropic").lower()

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


def extract_json(raw: str) -> dict:
    """Pull a JSON object out of a raw LLM response, stripping any prose or fences."""
    raw = raw.strip()
    # Strip markdown code fences
    if raw.startswith("```"):
        lines = raw.splitlines()
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        raw = "\n".join(lines).strip()
    # Find the outermost { ... }
    start = raw.find("{")
    end = raw.rfind("}") + 1
    if start == -1 or end <= start:
        raise ValueError("No JSON object found in response")
    return json.loads(raw[start:end])


async def call_anthropic(text: str) -> str:
    from anthropic import AsyncAnthropic

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise EnvironmentError("ANTHROPIC_API_KEY is not set")

    client = AsyncAnthropic(api_key=api_key)
    collected = []
    async with client.messages.stream(
        model="claude-opus-4-6",
        max_tokens=16000,
        thinking={"type": "adaptive"},
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": f"Parse this travel information into a structured itinerary:\n\n{text}"}],
    ) as stream:
        async for chunk in stream.text_stream:
            collected.append(chunk)
    return "".join(collected)


async def call_ollama(text: str) -> str:
    from openai import AsyncOpenAI

    base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
    model = os.getenv("OLLAMA_MODEL", "qwen2.5:7b")

    client = AsyncOpenAI(base_url=base_url, api_key="ollama")
    collected = []
    stream = await client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Parse this travel information into a structured itinerary:\n\n{text}"},
        ],
        stream=True,
        temperature=0.1,  # Low temperature for more reliable JSON output
    )
    async for chunk in stream:
        delta = chunk.choices[0].delta.content
        if delta:
            collected.append(delta)
    return "".join(collected)


@app.get("/")
async def root():
    return FileResponse("static/index.html")


@app.get("/api/config")
async def get_config():
    """Tell the frontend which backend is active."""
    return {"backend": BACKEND, "model": os.getenv("OLLAMA_MODEL", "qwen2.5:7b") if BACKEND == "ollama" else "claude-opus-4-6"}


@app.post("/api/generate")
async def generate_itinerary(request: Request):
    body = await request.json()
    text = body.get("text", "").strip()

    if not text:
        return JSONResponse({"error": "No travel information provided"}, status_code=400)

    async def event_stream():
        def sse(payload: dict) -> str:
            return f"data: {json.dumps(payload)}\n\n"

        try:
            yield sse({"type": "status", "message": "Analyzing your travel information..."})

            if BACKEND == "ollama":
                model = os.getenv("OLLAMA_MODEL", "qwen2.5:7b")
                yield sse({"type": "status", "message": f"Running {model} locally..."})
                raw = await call_ollama(text)
            else:
                yield sse({"type": "status", "message": "Building your itinerary with Claude..."})
                raw = await call_anthropic(text)

            itinerary = extract_json(raw)
            yield sse({"type": "complete", "data": itinerary})

        except EnvironmentError as e:
            yield sse({"type": "error", "message": str(e)})
        except json.JSONDecodeError:
            yield sse({"type": "error", "message": "The model returned invalid JSON. Try again, or switch to a more capable model."})
        except ValueError as e:
            yield sse({"type": "error", "message": str(e)})
        except Exception as e:
            msg = str(e)
            if "authentication" in msg.lower() or "api_key" in msg.lower():
                msg = "Invalid API key. Please check your ANTHROPIC_API_KEY."
            elif "rate_limit" in msg.lower():
                msg = "Rate limit reached. Please wait a moment and try again."
            elif "connection" in msg.lower() or "refused" in msg.lower():
                msg = f"Could not connect to Ollama. Is it running? (ollama serve)"
            yield sse({"type": "error", "message": msg})
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
