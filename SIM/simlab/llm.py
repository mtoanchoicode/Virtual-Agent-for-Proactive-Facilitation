"""Thin OpenAI wrapper returning schema-validated JSON, with token accounting."""
import json
from typing import Optional

from openai import AsyncOpenAI


class LLM:
    def __init__(self, model: str, temperature: float = 0.8):
        self.client = AsyncOpenAI()
        self.model = model
        self.temperature = temperature
        self.prompt_tokens = 0
        self.completion_tokens = 0

    async def json(self, system: str, user: str, name: str, schema: dict,
                   temperature: Optional[float] = None, model: Optional[str] = None) -> dict:
        res = await self.client.chat.completions.create(
            model=model or self.model,
            temperature=self.temperature if temperature is None else temperature,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            response_format={"type": "json_schema",
                             "json_schema": {"name": name, "strict": True, "schema": schema}},
        )
        if res.usage:
            self.prompt_tokens += res.usage.prompt_tokens
            self.completion_tokens += res.usage.completion_tokens
        return json.loads(res.choices[0].message.content)


def obj(**props) -> dict:
    """Strict JSON-schema object: every property required, no extras."""
    return {"type": "object", "properties": props, "required": list(props), "additionalProperties": False}
