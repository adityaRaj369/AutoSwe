"""arq worker entrypoint. Run with: arq app.queue.worker.WorkerSettings"""

from __future__ import annotations

from app.queue.config import redis_settings
from app.queue.processor import process_run as run_processor
from app.utils.logger import configure_logging


async def process_run(ctx: dict, run_id: str) -> None:
    await run_processor(run_id)


async def on_startup(ctx: dict) -> None:
    configure_logging()


class WorkerSettings:
    functions = [process_run]
    on_startup = on_startup
    redis_settings = redis_settings()
    max_jobs = 1
    max_tries = 1
    job_timeout = 60 * 30  # 30 minutes per run
