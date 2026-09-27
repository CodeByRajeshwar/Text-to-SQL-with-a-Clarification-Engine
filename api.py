"""
api.py
------
FastAPI wrapper around the exact same pipeline main.py uses (clarifier ->
sql_generator -> database -> responder). Nothing in those modules changes --
this file just exposes them over HTTP instead of a terminal input() loop.

Run with:
    uvicorn api:app --reload

Then open http://127.0.0.1:8000/docs for interactive Swagger docs, or:

    curl -X POST http://127.0.0.1:8000/ask \
      -H "Content-Type: application/json" \
      -d '{"question": "top customers of 2026"}'

Flow for the client (e.g. a frontend):
  1. POST /ask {"question": "..."}
     -> if status="ambiguous": show `reasoning` + `options` to the user,
        including the free-text escape hatch (there is no numbered "0" here
        -- the client just lets the user type anything and sends it as
        `question` to /clarify).
     -> if status="answered": done, show the answer.
     -> if status="error": show `message`.
  2. If ambiguous, the client picks one option's `clarified_question` value
     (or the user's own typed text) and calls:
     POST /clarify {"question": "<that text>"}
     -> same status/answered/error shape as above.
"""

from typing import List, Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.config import LLM_PROVIDER
from app.clarifier import classify_ambiguity
from app.sql_generator import generate_sql
from app.database import run_query, UnsafeSQLError, SQLExecutionError
from app.responder import correct_sql, summarize_result

app = FastAPI(
    title="Text-to-SQL with Clarification Engine",
    description="Ask questions about the company database in plain English.",
    version="1.0.0",
)

# Wide-open CORS for local development so a frontend on a different port
# (e.g. React on :3000) can call this freely. Tighten this before deploying
# anywhere public -- restrict allow_origins to your actual frontend's URL.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Request/response shapes
# ---------------------------------------------------------------------------

class QuestionRequest(BaseModel):
    question: str


class ClarifyOption(BaseModel):
    label: str
    clarified_question: str


class PipelineResponse(BaseModel):
    status: str  # "ambiguous" | "answered" | "error"

    # populated when status == "ambiguous"
    reasoning: Optional[str] = None
    options: Optional[List[ClarifyOption]] = None

    # populated when status == "answered"
    sql: Optional[str] = None
    explanation: Optional[str] = None
    row_count: Optional[int] = None
    sample_rows: Optional[List[dict]] = None
    answer: Optional[str] = None
    caveat: Optional[str] = None

    # populated when status == "error"
    message: Optional[str] = None


# ---------------------------------------------------------------------------
# Shared pipeline logic (generation -> execution -> self-correction -> summary)
# ---------------------------------------------------------------------------

def _run_pipeline(question: str) -> PipelineResponse:
    try:
        generation = generate_sql(question)
    except RuntimeError as e:
        return PipelineResponse(status="error", message=str(e))

    try:
        result = run_query(generation.sql)
    except UnsafeSQLError as e:
        return PipelineResponse(status="error", message=f"Refused to execute: {e}")
    except SQLExecutionError as e:
        try:
            fixed = correct_sql(question, generation.sql, str(e))
            result = run_query(fixed.sql)
            generation = fixed
        except (UnsafeSQLError, SQLExecutionError) as e2:
            return PipelineResponse(
                status="error",
                message=f"Query failed even after one correction attempt: {e2}",
            )
        except RuntimeError as e3:
            return PipelineResponse(status="error", message=str(e3))

    if result.is_empty():
        return PipelineResponse(
            status="answered",
            sql=generation.sql,
            explanation=generation.explanation,
            row_count=0,
            sample_rows=[],
            answer="No rows matched this query.",
        )

    try:
        summary = summarize_result(question, generation.sql, result)
    except RuntimeError as e:
        return PipelineResponse(status="error", message=str(e))

    return PipelineResponse(
        status="answered",
        sql=generation.sql,
        explanation=generation.explanation,
        row_count=len(result.rows),
        sample_rows=result.as_dicts()[:5],
        answer=summary.answer,
        caveat=summary.caveat,
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/health")
def health():
    return {"status": "ok", "provider": LLM_PROVIDER}


@app.post("/ask", response_model=PipelineResponse)
def ask(payload: QuestionRequest):
    """
    First call for any new question. Runs the ambiguity classifier; if the
    question is ambiguous, returns interpretations for the client to present
    (the client should also offer its own free-text option -- there's no
    numbered "0" here, that was a CLI-only convenience).
    """
    try:
        check = classify_ambiguity(payload.question)
    except RuntimeError as e:
        return PipelineResponse(status="error", message=str(e))

    if check.is_ambiguous and check.interpretations:
        return PipelineResponse(
            status="ambiguous",
            reasoning=check.reasoning,
            options=[
                ClarifyOption(label=i.label, clarified_question=i.clarified_question)
                for i in check.interpretations
            ],
        )

    return _run_pipeline(payload.question)


@app.post("/clarify", response_model=PipelineResponse)
def clarify(payload: QuestionRequest):
    """
    Second call, only needed after /ask returned status="ambiguous". Send
    back whichever interpretation's `clarified_question` the user picked, or
    their own custom text. Skips re-classification and goes straight to SQL
    generation, since the question is already treated as unambiguous.
    """
    return _run_pipeline(payload.question)
