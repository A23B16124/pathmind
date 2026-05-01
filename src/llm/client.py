from openai import AsyncOpenAI

VLLM_BASE = "http://localhost:8000/v1"
MODEL = "Qwen/Qwen2.5-72B-Instruct"

_client = AsyncOpenAI(api_key="EMPTY", base_url=VLLM_BASE)


async def chat(messages: list[dict], temperature: float = 0.1, max_tokens: int = 2048) -> str:
    resp = await _client.chat.completions.create(
        model=MODEL, messages=messages, temperature=temperature, max_tokens=max_tokens,
    )
    return resp.choices[0].message.content
