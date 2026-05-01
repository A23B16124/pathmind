import asyncio
from src.llm.client import chat


async def run_agents(agent_calls: list[tuple[str, list[dict]]]) -> dict[str, str]:
    async def _call(name: str, messages: list[dict]):
        return name, await chat(messages)
    results = await asyncio.gather(*[_call(n, m) for n, m in agent_calls])
    return dict(results)
