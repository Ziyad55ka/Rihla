"""Spike: first simple test of the Gemini connection.

This is an experiment, not app code. It checks three things:
  1. The API key works.
  2. Which Gemini models your key can use.
  3. Google Search grounding returns an answer with real source links.

Run from the backend folder:
    uv run python spikes/gemini_hello.py
"""

import os
import sys
from pathlib import Path

from google import genai
from google.genai import types

# --- 1) Read GEMINI_API_KEY (and optional GEMINI_MODEL) from backend/.env ---
ENV_FILE = Path(__file__).resolve().parent.parent / ".env"


def read_env(name: str) -> str | None:
    if os.environ.get(name):
        return os.environ[name]
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            if line.strip().startswith(f"{name}="):
                return line.split("=", 1)[1].strip().strip('"') or None
    return None


api_key = read_env("GEMINI_API_KEY")
if not api_key:
    sys.exit("GEMINI_API_KEY is missing. Add it to backend/.env and try again.")

client = genai.Client(api_key=api_key)

# --- 2) List the Gemini models this key can use ---
print("Models available to your key:")
flash_models = []
for model in client.models.list():
    name = model.name.removeprefix("models/")
    if "gemini" in name and "generateContent" in (model.supported_actions or []):
        print("  -", name)
        if "flash" in name:
            flash_models.append(name)

model_name = read_env("GEMINI_MODEL") or (
    sorted(flash_models)[-1] if flash_models else "gemini-flash-latest"
)
print(f"\nUsing model: {model_name}\n")

# --- 3) A small travel question with Google Search turned on ---
question = (
    "Suggest one 4-day trip from Riyadh in late November for a group of 4 "
    "with a budget of about 3000 SAR per person. Name the destination, one "
    "real hotel, and the typical flight time. Keep it short."
)

response = client.models.generate_content(
    model=model_name,
    contents=question,
    config=types.GenerateContentConfig(
        tools=[types.Tool(google_search=types.GoogleSearch())],
    ),
)

print("Answer:\n")
print(response.text)

# --- 4) Print the sources Gemini used (this is what "grounding" gives us) ---
meta = response.candidates[0].grounding_metadata if response.candidates else None
chunks = (meta.grounding_chunks or []) if meta else []
print(f"\nSources found: {len(chunks)}")
for chunk in chunks:
    if chunk.web:
        print("  -", chunk.web.title, "->", chunk.web.uri)

if response.usage_metadata:
    print("\nTokens used:", response.usage_metadata.total_token_count)
