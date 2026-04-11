"""Shared helper for OpenAI chat completion calls.

Handles the parameter differences between model families:
- gpt-4* and gpt-3.5* use `max_tokens` and allow custom `temperature`
- gpt-5* uses `max_completion_tokens` and only allows the default temperature (1)

Usage:
    from app.services.llm_helper import build_openai_params

    client = openai.AsyncOpenAI(api_key=settings.openai_api_key)
    params = build_openai_params(
        model=settings.bias_scoring_model,
        prompt=prompt,
        max_tokens=1024,
        temperature=0.3,
    )
    response = await client.chat.completions.create(**params)
"""


def build_openai_params(
    model: str,
    prompt: str,
    max_tokens: int = 1024,
    temperature: float = 0.3,
) -> dict:
    """Return kwargs dict for openai chat.completions.create.

    Adapts parameter names for gpt-5-family models which:
    - use `max_completion_tokens` instead of `max_tokens`
    - only support temperature=1 (the default), so we omit it
    """
    params: dict = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
    }
    if model.startswith("gpt-5"):
        params["max_completion_tokens"] = max_tokens
        # gpt-5 family rejects explicit temperature != 1
    else:
        params["max_tokens"] = max_tokens
        params["temperature"] = temperature
    return params
