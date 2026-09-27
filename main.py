"""
main.py
-------
Orchestrates the full pipeline:

  user question
       |
       v
  [clarifier.classify_ambiguity]  -- ambiguous? ask user to pick an interpretation
       |                              (or let them type their own if none fit)
       v
  [sql_generator.generate_sql]    -- NL -> SQL (few-shot + Pydantic-forced JSON)
       |
       v
  [database.run_query]            -- execute against SQLite (read-only guarded)
       |         \\
       |          -> on sqlite3 error: [responder.correct_sql] -> retry once
       v
  [responder.summarize_result]    -- rows -> natural-language answer
       |
       v
  printed to user

Run with: python main.py
"""

from app.clarifier import classify_ambiguity
from app.sql_generator import generate_sql
from app.database import run_query, UnsafeSQLError, SQLExecutionError
from app.responder import correct_sql, summarize_result


def resolve_question(raw_question: str) -> str:
    """
    Run the clarification engine. If the question is ambiguous, present the
    classifier's interpretations, but also always offer a "type your own"
    escape hatch (option 0) -- our guessed interpretations won't always
    match what the user actually meant, so they shouldn't be boxed into
    picking the closest-but-wrong option. Returns a question that is safe
    to hand directly to the SQL generator.
    """
    check = classify_ambiguity(raw_question)

    if not check.is_ambiguous or not check.interpretations:
        return raw_question

    print(f"\n{check.reasoning}")
    print("\nHere's what I can run:\n")
    for i, interp in enumerate(check.interpretations, 1):
        print(f"  {i}. {interp.label}")
    print("  0. Something else -- let me type exactly what I mean")

    while True:
        choice = input(f"\nEnter 0-{len(check.interpretations)}: ").strip()
        if choice == "0":
            custom = input("What would you like to ask instead? ").strip()
            if custom:
                return custom
            print("Please enter a question.")
            continue
        if choice.isdigit() and 1 <= int(choice) <= len(check.interpretations):
            return check.interpretations[int(choice) - 1].clarified_question
        print("Please enter a valid number.")


def answer_question(question: str) -> None:
    """Run generation -> execution (with one self-correction retry) -> summary."""
    generation = generate_sql(question)
    print(f"\nGenerated SQL:\n  {generation.sql}")
    print(f"Assumption: {generation.explanation}")

    try:
        result = run_query(generation.sql)
    except UnsafeSQLError as e:
        print(f"\nRefused to execute: {e}")
        return
    except SQLExecutionError as e:
        print(f"\nQuery failed to execute ({e}); attempting one correction...")
        fixed = correct_sql(question, generation.sql, str(e))
        print(f"Corrected SQL:\n  {fixed.sql}")
        try:
            result = run_query(fixed.sql)
            generation = fixed
        except (UnsafeSQLError, SQLExecutionError) as e2:
            print(f"\nCorrection also failed: {e2}")
            return

    if result.is_empty():
        print("\nNo rows returned.")
        return

    print(f"\n{len(result.rows)} row(s) returned. Sample:")
    for row in result.as_dicts()[:5]:
        print(" ", row)

    summary = summarize_result(question, generation.sql, result)
    print(f"\nAnswer: {summary.answer}")
    if summary.caveat:
        print(f"Note: {summary.caveat}")


def main() -> None:
    print("Text-to-SQL with Clarification Engine (type 'quit' to exit)")
    print("Database: company.db\n")

    while True:
        raw_question = input("Ask a question about the company data: ").strip()
        if raw_question.lower() in {"quit", "exit"}:
            break
        if not raw_question:
            continue

        try:
            resolved_question = resolve_question(raw_question)
            answer_question(resolved_question)
        except RuntimeError as e:
            print(f"\nError: {e}")

        print("\n" + "-" * 60 + "\n")


if __name__ == "__main__":
    main()
