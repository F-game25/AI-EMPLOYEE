"""Small async helpers used across the neural_brain package."""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Awaitable, Callable

logger = logging.getLogger(__name__)


def fire_and_forget(coro: Awaitable[Any], *, name: str = "nb_task") -> asyncio.Task | None:
    """Schedule a coroutine if a loop is running; otherwise return None.

    Safe to call from sync contexts: if no event loop exists, the coroutine is
    *not* awaited (caller should treat the work as best-effort).
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        try:
            asyncio.run(coro)  # type: ignore[arg-type]
            return None
        except Exception as e:
            logger.warning("%s sync-run failed: %s", name, e)
            return None
    task = loop.create_task(coro, name=name)  # type: ignore[arg-type]

    def _swallow(t: asyncio.Task) -> None:
        if t.cancelled():
            return
        exc = t.exception()
        if exc is not None:
            logger.warning("%s failed: %s", name, exc)

    task.add_done_callback(_swallow)
    return task


async def gather_with_timeout(
    *aws: Awaitable[Any],
    timeout: float = 5.0,
) -> list[Any]:
    """asyncio.gather with a per-call timeout; failures become None."""
    async def _wrap(aw: Awaitable[Any]) -> Any:
        try:
            return await asyncio.wait_for(aw, timeout=timeout)
        except Exception as e:
            logger.debug("gather_with_timeout entry failed: %s", e)
            return None

    return await asyncio.gather(*[_wrap(a) for a in aws])


def run_blocking(fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Awaitable[Any]:
    """Wrap a blocking call into the default executor."""
    loop = asyncio.get_running_loop()
    return loop.run_in_executor(None, lambda: fn(*args, **kwargs))
