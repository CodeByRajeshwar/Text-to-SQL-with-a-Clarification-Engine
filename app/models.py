"""
models.py
---------
Pydantic models = the contract between us and the LLM. Each one is passed
directly to Anthropic's Structured Outputs (`output_format=<Model>` in
client.messages.parse()), which compiles it into a grammar the model is
constrained to follow. This is what your slide meant by "force an LLM to
give you a specific JSON format" -- it's stronger than prompting for JSON,
because the API guarantees schema compliance rather than just requesting it.
"""

from typing import List, Optional
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Step 4: Clarification Engine
# ---------------------------------------------------------------------------

class Interpretation(BaseModel):
    """One possible reading of an ambiguous question."""
    label: str = Field(
        description="Short human-readable label for this interpretation, "
                    "shown to the user as a choice, e.g. 'By total spend'."
    )
    clarified_question: str = Field(
        description="The original question rewritten to be unambiguous under "
                    "this interpretation, ready to hand to the SQL generator."
    )


class AmbiguityCheck(BaseModel):
    """Output of the classifier LLM call."""
    is_ambiguous: bool = Field(
        description="True if the question has more than one reasonable, "
                    "materially different interpretation given the schema."
    )
    reasoning: str = Field(
        description="One or two sentences explaining why the question is or "
                    "isn't ambiguous."
    )
    interpretations: List[Interpretation] = Field(
        default_factory=list,
        description="2-4 possible interpretations, ONLY populated when "
                    "is_ambiguous is true. Empty list otherwise.",
    )


# ---------------------------------------------------------------------------
# Step 3: Text-to-SQL generation
# ---------------------------------------------------------------------------

class SQLGeneration(BaseModel):
    """Output of the SQL-generation LLM call."""
    sql: str = Field(
        description="A single valid SQLite SELECT statement that answers the "
                    "question. No markdown fences, no comments, no trailing "
                    "explanation -- SQL only."
    )
    explanation: str = Field(
        description="One sentence, in plain language, describing what the "
                    "query does and which assumption it makes (e.g. date "
                    "range, join type, metric definition)."
    )


# ---------------------------------------------------------------------------
# Step 5: Natural-language answer formatting
# ---------------------------------------------------------------------------

class NaturalAnswer(BaseModel):
    """Output of the final response-formatting LLM call."""
    answer: str = Field(
        description="A concise, direct natural-language answer to the "
                    "user's original question, grounded only in the provided "
                    "query results."
    )
    caveat: Optional[str] = Field(
        default=None,
        description="Optional short caveat if the result set was truncated, "
                    "empty, or relies on an assumption worth flagging.",
    )
