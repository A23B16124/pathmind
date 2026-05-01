import json
import re
from pydantic import BaseModel, ValidationError
from typing import TypeVar, Type

T = TypeVar("T", bound=BaseModel)


def extract_json(text: str) -> str:
    m = re.search(r"```json\s*([\s\S]+?)\s*```", text)
    if m:
        return m.group(1)
    m = re.search(r"\{[\s\S]+\}", text)
    if m:
        return m.group(0)
    raise ValueError("Aucun JSON trouvé dans la réponse")


def parse_agent_output(raw: str, schema: Type[T], retries: int = 2) -> T:
    last_error = None
    for _ in range(retries + 1):
        try:
            return schema.model_validate(json.loads(extract_json(raw)))
        except (ValueError, ValidationError) as e:
            last_error = e
    raise RuntimeError(f"Parse failed après {retries} tentatives : {last_error}\n---\n{raw[:500]}")
