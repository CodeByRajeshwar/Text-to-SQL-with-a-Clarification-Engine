"""
clarifier.py
------------
Step 4 from the build guide: before generating SQL, ask a classifier LLM
whether the question is ambiguous given the schema, and if so, what the
distinct interpretations are.
"""

from app.db_schema import SCHEMA_DESCRIPTION
from app.models import AmbiguityCheck
from app.llm_client import structured_call

CLASSIFIER_SYSTEM_PROMPT = f"""You are an ambiguity classifier for a text-to-SQL system.

Given a user's natural-language question and the database schema below,
decide whether the question has more than one reasonable, MATERIALLY
DIFFERENT interpretation that would produce different SQL / different
numeric results.

Do NOT flag a question as ambiguous just because it could theoretically be
phrased more precisely. Only flag it if a competent analyst could honestly
justify two different queries that give two different answers. Common real
sources of ambiguity in this schema: vague superlatives ("best", "top"),
undefined time windows ("recent", "last month"), whether to include entities
with zero related rows (inner vs. left join), and metric definitions
("revenue" as gross vs. net of refunds).

If ambiguous, produce 2-4 interpretations. Each interpretation must include
a fully rewritten, self-contained version of the question that resolves the
ambiguity explicitly (e.g. "which customer has the highest total order
value" instead of "who is the best customer").

TONE FOR THE `reasoning` FIELD:
Write it the way a friendly, competent analyst would ask a quick follow-up
question in conversation -- not a technical audit note. It should read as
a natural spoken clarifying question, not a list of ambiguity categories.

  BAD  (clinical, itemized): "The term 'revenue' is ambiguous; it could
        refer to gross order totals or net cash collected. Also 'this
        year' needs to be explicitly defined relative to today's date."

  GOOD (conversational, single flowing question): "When you say
        'revenue,' do you mean the full order totals, or the actual cash
        collected after refunds? And just to be safe, should 'this year'
        mean the current calendar year, or the last 12 months?"

Keep it to one or two short sentences, phrased as a genuine question to the
user, not a statement about the question.

SCHEMA:
{SCHEMA_DESCRIPTION}
"""


def classify_ambiguity(question: str) -> AmbiguityCheck:
    """Run the classifier and return a validated AmbiguityCheck."""
    user_prompt = f"User question: {question}"
    return structured_call(
        system_prompt=CLASSIFIER_SYSTEM_PROMPT,
        user_prompt=user_prompt,
        output_model=AmbiguityCheck,
    )
