"""
sql_generator.py
----------------
Step 3 from the build guide: turn a (now-unambiguous) natural-language
question into a single SQLite SELECT statement.

Uses the schema description + few-shot examples from db_schema.py, and
forces the output shape via Pydantic (models.SQLGeneration) so we always
get back exactly {sql, explanation} with no parsing gymnastics.
"""

from app.db_schema import SCHEMA_DESCRIPTION, format_few_shot_block
from app.models import SQLGeneration
from app.llm_client import structured_call

SQL_GENERATOR_SYSTEM_PROMPT = f"""You are a SQL generator for a SQLite database.

Rules:
- Generate exactly ONE valid SQLite SELECT statement. Never INSERT, UPDATE,
  DELETE, DROP, ALTER, or any other statement that modifies data or schema.
- Use ONLY the tables and columns defined in the schema below. Never invent
  table or column names.
- Use table aliases for readability in joins.
- Prefer explicit column lists over SELECT *.
- If the question involves a relative date ("this month", "last year"),
  compute it relative to the fixed "today" given in the schema notes below,
  not the current real-world date.
- Put the finished statement in the `sql` field only -- no markdown fences,
  no trailing comments, no explanation text inside that field.

SCHEMA:
{SCHEMA_DESCRIPTION}

FEW-SHOT EXAMPLES (follow this style and exact column/table naming):
{format_few_shot_block()}
"""


def generate_sql(clarified_question: str) -> SQLGeneration:
    """Generate SQL for a question that is already unambiguous."""
    user_prompt = f"Question: {clarified_question}"
    return structured_call(
        system_prompt=SQL_GENERATOR_SYSTEM_PROMPT,
        user_prompt=user_prompt,
        output_model=SQLGeneration,
        max_tokens=1024,
    )
