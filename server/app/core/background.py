"""In-process background tasks: work that should outlive the request that started it
(AI analysis, video compression) without a separate worker process. Tasks run on the API
process's own event loop — so they die with it: whoever schedules work here must also
recover rows a restart left half-done (see `fail_interrupted_analyses`,
`fail_interrupted_compressions`, both run at startup).
"""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from typing import Any

# Strong references to in-flight tasks (asyncio itself only keeps weak ones, so an
# unreferenced task can be garbage-collected mid-run).
_tasks: set[asyncio.Task] = set()


def schedule(coro: Coroutine[Any, Any, Any]) -> asyncio.Task:
    task = asyncio.create_task(coro)
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)
    return task


async def wait_for_background_jobs() -> None:
    """Waits until every scheduled task (including ones scheduled meanwhile) is done.
    Used by tests; exceptions are the tasks' own business and are not re-raised here."""
    while _tasks:
        await asyncio.gather(*list(_tasks), return_exceptions=True)
