import os
from openai import AsyncOpenAI
from dotenv import load_dotenv

load_dotenv()

_client = AsyncOpenAI(
    api_key=os.getenv("ANTHROPIC_API_KEY", "dummy"),
    base_url=os.getenv("LLM_BASE_URL", "https://api.anthropic.com/v1"),
)
MODEL = os.getenv("LLM_MODEL", "claude-sonnet-4-6")

async def chat(messages: list[dict], system: str = "", max_tokens: int = 2000) -> str:
    full_messages = []
    if system:
        full_messages.append({"role": "system", "content": system})
    full_messages.extend(messages)
    try:
        resp = await _client.chat.completions.create(
            model=MODEL,
            max_tokens=max_tokens,
            messages=full_messages,
        )
        return resp.choices[0].message.content or ""
    except Exception as e:
        return f"[LLM error: {e}]"
