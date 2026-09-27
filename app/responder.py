"""
responder.py
------------
Step 5 from the build guide: format execution results for the user.

Two responsibilities:
1. `correct_sql` -- if execution throws a sqlite3 error (bad column, syntax
   slip), feed the error back to the LLM for ONE retry. This handles the
   common case where the model referenced a slightly wrong name.
2. `summarize_result` -- turn the raw rows into a natural-language answer
   grounded strictly in what the query returned (no hallucinated numbers).
"""

import json

from app.config import MAX_ROWS_FOR_SUMMARY
from app.db_schema import SCHEMA_DESCRIPTION
from app.models import SQLGeneration, NaturalAnswer
from app.database import QueryResult
from app.llm_client import structured_call

# ---------------------------------------------------------------------------
# SQL self-correction (one retry on execution error)
# ---------------------------------------------------------------------------

CORRECTION_SYSTEM_PROMPT = f"""You are a SQL debugger for a SQLite database.

The previous SQL query failed to execute. You will be given the original
question, the SQL that failed, and the exact database error. Fix the query.

Rules are identical to normal generation:
- Exactly one valid SQLite SELECT statement.
- Only use tables/columns from the schema below.
- No markdown fences, no explanation text inside the `sql` field.

SCHEMA:
{SCHEMA_DESCRIPTION}
"""


def correct_sql(question: str, failed_sql: str, error_message: str) -> SQLGeneration:
    """One-shot retry: ask the LLM to fix a query that failed to execute."""
    user_prompt = (
        f"Original question: {question}\n\n"
        f"SQL that failed:\n{failed_sql}\n\n"
        f"Database error:\n{error_message}\n\n"
        "Provide a corrected query."
    )
    return structured_call(
        system_prompt=CORRECTION_SYSTEM_PROMPT,
        user_prompt=user_prompt,
        output_model=SQLGeneration,
        max_tokens=1024,
    )


# ---------------------------------------------------------------------------
# Natural-language summarization
# ---------------------------------------------------------------------------

RESPONDER_SYSTEM_PROMPT = """You are a helpful data analyst assistant.

You will be given the user's original question and the JSON rows returned
by a SQL query that answers it. Write a concise, direct natural-language
answer using ONLY the data provided -- never invent numbers or rows that
aren't in the data. If the result set is empty, say so plainly rather than
guessing why.
"""


def summarize_result(question: str, sql: str, result: QueryResult) -> NaturalAnswer:
    """Turn raw query rows into a natural-language answer."""
    rows = result.as_dicts()
    truncated = len(rows) > MAX_ROWS_FOR_SUMMARY
    rows_for_prompt = rows[:MAX_ROWS_FOR_SUMMARY]

    user_prompt = (
        f"Original question: {question}\n\n"
        f"SQL executed:\n{sql}\n\n"
        f"Result rows (JSON, {len(rows)} total"
        + (f", showing first {MAX_ROWS_FOR_SUMMARY}" if truncated else "")
        + f"):\n{json.dumps(rows_for_prompt, default=str)}"
    )

    return structured_call(
        system_prompt=RESPONDER_SYSTEM_PROMPT,
        user_prompt=user_prompt,
        output_model=NaturalAnswer,
        max_tokens=1024,
    )
