import pytest
from unittest.mock import AsyncMock, patch
from src.llm.parser import extract_json, parse_agent_output
from src.schemas import QCOutput


def test_extract_json_from_markdown():
    text = '```json\n{"verdict": "ok", "issues": [], "confidence": 0.9, "challenged_fields": []}\n```'
    result = extract_json(text)
    assert '"verdict"' in result


def test_extract_json_bare():
    text = '{"verdict": "ok", "issues": [], "confidence": 0.8, "challenged_fields": []}'
    assert extract_json(text).startswith("{")


def test_extract_json_not_found():
    with pytest.raises(ValueError):
        extract_json("No JSON here at all")


def test_parse_agent_output_valid():
    raw = '```json\n{"verdict": "ok", "issues": [], "confidence": 0.95, "challenged_fields": []}\n```'
    output = parse_agent_output(raw, QCOutput)
    assert output.verdict == "ok"


def test_parse_agent_output_invalid():
    raw = '{"verdict": "invalid_value", "issues": [], "confidence": 0.5}'
    with pytest.raises(RuntimeError):
        parse_agent_output(raw, QCOutput, retries=0)


@pytest.mark.asyncio
async def test_run_agents_parallel():
    from src.llm.multi_agent import run_agents
    with patch("src.llm.multi_agent.chat", new_callable=AsyncMock) as mock_chat:
        mock_chat.return_value = "response"
        calls = [("agent_a", [{"role": "user", "content": "hello"}]),
                 ("agent_b", [{"role": "user", "content": "world"}])]
        results = await run_agents(calls)
    assert set(results.keys()) == {"agent_a", "agent_b"}
    assert mock_chat.call_count == 2
