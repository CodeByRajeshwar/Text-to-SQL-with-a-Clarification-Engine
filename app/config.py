"""
config.py
---------
Central place for settings. Reads API keys from the environment (never
hardcode them). Uses python-dotenv so you can keep them in a local .env
file during development.

LLM_PROVIDER switches which backend llm_client.py talks to:
  - "groq" (default): Groq Inc. -- hosts open-weight models (Llama,
    gpt-oss, etc.) on fast inference hardware. Has a genuine free tier.
  - "gemini": Google Gemini API. Also has a genuine free tier, kept as a
    fallback option.

xAI/Grok support has been intentionally removed from this project.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()  # loads variables from a .env file in the project root, if present

LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "groq").lower()  # "groq" or "gemini"

# --- Groq Inc. ---
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
# openai/gpt-oss-120b has full Structured Outputs support (strict JSON
# schema conformance) per Groq's own docs. Check
# https://console.groq.com/docs/models for the current supported-model list.
GROQ_MODEL = os.environ.get("GROQ_MODEL", "openai/gpt-oss-120b")

# --- Gemini ---
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")

# --- Database ---
# IMPORTANT: default to an ABSOLUTE path next to this config.py file, not a
# bare "company.db". sqlite3.connect() does NOT error if a file is missing --
# it silently creates a new, empty database at that path. Pinning an
# absolute path here means "which folder did I launch python from" can
# never change which database file gets opened.
# __file__ is .../text2sql-clarification-engine/app/config.py, so parent.parent
# is the repo root. company.db lives in <repo root>/data/company.db.
_REPO_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_DB_PATH = str(_REPO_ROOT / "data" / "company.db")
DB_PATH = os.environ.get("DB_PATH", _DEFAULT_DB_PATH)

# Safety: max rows returned to the LLM for summarization, to avoid blowing
# past context limits on large result sets.
MAX_ROWS_FOR_SUMMARY = 50

if LLM_PROVIDER not in ("groq", "gemini"):
    raise RuntimeError(f"LLM_PROVIDER must be 'groq' or 'gemini', got: {LLM_PROVIDER!r}")

if LLM_PROVIDER == "groq" and not GROQ_API_KEY:
    raise RuntimeError(
        "GROQ_API_KEY is not set. Get a free key at https://console.groq.com/keys "
        "and put it in your .env file (see .env.example)."
    )

if LLM_PROVIDER == "gemini" and not GEMINI_API_KEY:
    raise RuntimeError(
        "GEMINI_API_KEY is not set. Get a free key at https://aistudio.google.com/apikey "
        "and put it in your .env file (see .env.example)."
    )
