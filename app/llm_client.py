"""
llm_client.py
-------------
One shared helper for every structured LLM call in the pipeline.

Dispatches to Groq Inc. or Google Gemini based on config.LLM_PROVIDER. Both
paths return the exact same thing: a validated instance of the Pydantic
model you asked for. Nothing else in the project (clarifier.py,
sql_generator.py, responder.py) needs to know or care which provider is
active -- they all just call structured_call(...).

Groq Inc. path (default): uses Groq's official `groq` SDK. Groq's API is
OpenAI-compatible and supports Structured Outputs via
response_format={"type": "json_schema", "json_schema": {...}} built from
model_json_schema(). There's no single-call ".parse()" helper in the groq
package, so we build the schema ourselves and validate the returned JSON
string against the Pydantic model directly.

Gemini path: uses google-genai's native response_schema=<PydanticModel>
support. response.parsed comes back as an already-validated instance.
"""

from typing import Type, TypeVar
from pydantic import BaseModel

from app.config import (
    LLM_PROVIDER,
    GROQ_API_KEY,
    GROQ_MODEL,
    GEMINI_API_KEY,
    GEMINI_MODEL,
)

T = TypeVar("T", bound=BaseModel)

DEFAULT_MAX_TOKENS = 2048


def _call_groq(system_prompt: str, user_prompt: str, output_model: Type[T], max_tokens: int) -> T:
    from groq import Groq

    client = Groq(api_key=GROQ_API_KEY)
    response = client.chat.completions.create(
        model=GROQ_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        response_format={
            "type": "json_schema",
            "json_schema": {
                "name": output_model.__name__,
                "schema": output_model.model_json_schema(),
            },
        },
        max_tokens=max_tokens,
    )

    content = response.choices[0].message.content
    if not content:
        raise RuntimeError(
            "Groq returned an empty response. This can happen if the "
            f"selected model ({GROQ_MODEL}) doesn't support Structured "
            "Outputs -- check https://console.groq.com/docs/structured-outputs "
            "for the current supported-model list."
        )

    try:
        return output_model.model_validate_json(content)
    except Exception as e:
        raise RuntimeError(
            f"Groq's response did not match the expected schema: {e}\n"
            f"Raw response was: {content!r}"
        ) from e


def _call_gemini(system_prompt: str, user_prompt: str, output_model: Type[T], max_tokens: int) -> T:
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=GEMINI_API_KEY)
    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=user_prompt,
        config=types.GenerateContentConfig(
            system_instruction=system_prompt,
            response_mime_type="application/json",
            response_schema=output_model,
            max_output_tokens=max_tokens,
            thinking_config=types.ThinkingConfig(thinking_budget=0),
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        ),
    )

    if response.parsed is None:
        finish_reason = None
        if response.candidates:
            finish_reason = response.candidates[0].finish_reason
        raise RuntimeError(
            "Gemini did not return a schema-conformant response "
            f"(finish_reason={finish_reason}). Try raising DEFAULT_MAX_TOKENS "
            f"in llm_client.py. Raw text was: {response.text!r}"
        )
    return response.parsed


def structured_call(
    system_prompt: str,
    user_prompt: str,
    output_model: Type[T],
    max_tokens: int = DEFAULT_MAX_TOKENS,
) -> T:
    """
    Call the configured LLM provider (config.LLM_PROVIDER) and get back a
    validated instance of `output_model`.
    """
    if LLM_PROVIDER == "groq":
        return _call_groq(system_prompt, user_prompt, output_model, max_tokens)
    elif LLM_PROVIDER == "gemini":
        return _call_gemini(system_prompt, user_prompt, output_model, max_tokens)
    else:
        raise RuntimeError(f"Unknown LLM_PROVIDER: {LLM_PROVIDER!r}")
