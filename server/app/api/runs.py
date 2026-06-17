"""Run endpoints: list, detail, stats, manual trigger."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import crud
from app.db.base import get_session
from app.db.models import RunStatus
from app.db.schemas import (
    ManualRunRequest,
    PaginatedRuns,
    RunDetail,
    RunSummary,
    StatsOut,
)
from app.github.client import GitHubClient
from app.queue.config import enqueue_run
from app.utils.logger import get_logger

log = get_logger("api.runs")
router = APIRouter(prefix="/api/runs", tags=["runs"])


@router.get("/stats", response_model=StatsOut)
async def get_stats(session: AsyncSession = Depends(get_session)) -> StatsOut:
    data = await crud.compute_stats(session)
    data["recent"] = [RunSummary.model_validate(r) for r in data["recent"]]
    return StatsOut(**data)


@router.get("", response_model=PaginatedRuns)
async def list_runs(
    repository_id: str | None = None,
    status: RunStatus | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
) -> PaginatedRuns:
    rows, total = await crud.list_runs(
        session, repository_id=repository_id, status=status, page=page, page_size=page_size
    )
    return PaginatedRuns(
        items=[RunSummary.model_validate(r) for r in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{run_id}", response_model=RunDetail)
async def get_run(run_id: str, session: AsyncSession = Depends(get_session)) -> RunDetail:
    run = await crud.get_run(session, run_id, with_steps=True)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return RunDetail.model_validate(run)


@router.post("/manual", response_model=RunSummary, status_code=202)
async def trigger_manual(
    req: ManualRunRequest, session: AsyncSession = Depends(get_session)
) -> RunSummary:
    repo = await crud.get_repository(session, req.repo_id)
    if repo is None:
        raise HTTPException(status_code=404, detail="Repository not found")

    issue_title, issue_body = await _fetch_issue_metadata(
        repo.owner, repo.name, req.issue_number, repo.installation_id
    )

    run = await crud.create_run(
        session,
        repository_id=repo.id,
        issue_number=req.issue_number,
        issue_title=issue_title,
        issue_body=issue_body,
        model=settings.agent_model_name,
    )
    await session.commit()
    await _dispatch(run.id)
    return RunSummary.model_validate(run)


async def _dispatch(run_id: str) -> None:
    """Enqueue via arq if Redis is reachable; otherwise run in-process."""
    try:
        await enqueue_run(run_id)
    except Exception as exc:
        log.warning("enqueue_failed_running_inline", error=str(exc))
        from app.queue.processor import process_run

        asyncio.create_task(process_run(run_id))


async def _fetch_issue_metadata(
    owner: str, repo: str, issue_number: int, installation_id: int | None
) -> tuple[str, str]:
    try:
        issue = await GitHubClient(installation_id=installation_id).get_issue(owner, repo, issue_number)
    except Exception as exc:
        log.warning(
            "manual_issue_fetch_failed",
            owner=owner,
            repo=repo,
            issue=issue_number,
            error=str(exc),
        )
        raise HTTPException(status_code=502, detail="Unable to fetch GitHub issue") from exc

    title = issue.get("title") or f"Issue #{issue_number}"
    body = issue.get("body") or ""
    return title, body
