import time
from functools import wraps

try:
    from langfuse import Langfuse
    _langfuse = Langfuse(public_key="lf_pk_pathmind", secret_key="lf_sk_pathmind", host="http://localhost:3100")
    _enabled = True
except Exception:
    _enabled = False


def trace_agent(agent_name: str):
    def decorator(fn):
        @wraps(fn)
        async def wrapper(*args, **kwargs):
            if not _enabled:
                return await fn(*args, **kwargs)
            span = _langfuse.span(name=agent_name)
            t0 = time.perf_counter()
            try:
                result = await fn(*args, **kwargs)
                span.update(metadata={"latency_ms": round((time.perf_counter() - t0) * 1000)}, level="DEFAULT")
                return result
            except Exception as e:
                span.update(level="ERROR", status_message=str(e))
                raise
            finally:
                span.end()
        return wrapper
    return decorator
