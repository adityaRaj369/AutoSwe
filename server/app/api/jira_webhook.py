"""Jira webhook receiver.

Starts an AutoSWE run when a Jira issue transitions into the configured
automation status (default: AutoSWE).
"""

from __future__ import annotations

import re
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import crud
from app.db.base import get_session
from app.queue.config import enqueue_run
from app.utils.logger import get_logger

log = get_logger("api.jira_webhook")
router = APIRouter(prefix="/api/webhook/jira", tags=["jira"])


@router.post("", status_code=202)
async def jira_webhook(
    payload: dict[str, Any],
    session: AsyncSession = Depends(get_session),
    secret: str | None = Query(default=None),
    x_autoswe_secret: str | None = Header(default=None),
) -> dict[str, Any]:
    _verify_secret(secret or x_autoswe_secret)

    if not _changed_to_autoswe(payload):
        return {"status": "ignored", "reason": "status_not_autoswe"}

    issue = payload.get("issue") or {}
    fields = issue.get("fields") or {}
    issue_key = issue.get("key")
    project_key = ((fields.get("project") or {}).get("key") or "").upper()
    if not issue_key or not project_key:
        raise HTTPException(status_code=400, detail="Jira payload is missing issue key/project")

    repo_target = settings.jira_repo_map.get(project_key)
    if repo_target is None:
        raise HTTPException(
            status_code=400,
            detail=f"No GitHub repo mapping configured for Jira project {project_key}",
        )
    owner, repo_name = repo_target

    existing = await crud.get_active_run_by_external_issue(
        session, source="jira", external_issue_key=issue_key
    )
    if existing is not None:
        return {"status": "already_running", "run_id": existing.id}

    repo = await crud.upsert_repository(session, owner=owner, name=repo_name)
    title = fields.get("summary") or issue_key
    body = _jira_issue_body(issue)
    issue_number = _issue_number(issue_key)
    issue_url = _issue_url(issue_key)

    run = await crud.create_run(
        session,
        repository_id=repo.id,
        issue_number=issue_number,
        issue_title=title,
        issue_body=body,
        model=settings.agent_model_name,
        source="jira",
        external_issue_key=issue_key,
        external_issue_url=issue_url,
    )
    await session.commit()
    await enqueue_run(run.id)
    log.info("jira_run_queued", run_id=run.id, issue=issue_key, repo=f"{owner}/{repo_name}")
    return {"status": "queued", "run_id": run.id, "issue_key": issue_key}


def _verify_secret(provided: str | None) -> None:
    if settings.jira_webhook_secret and provided != settings.jira_webhook_secret:
        raise HTTPException(status_code=401, detail="Invalid Jira webhook secret")


def _changed_to_autoswe(payload: dict[str, Any]) -> bool:
    target = settings.jira_auto_status.strip().lower()
    changelog = payload.get("changelog") or {}
    for item in changelog.get("items") or []:
        if str(item.get("field", "")).lower() != "status":
            continue
        if str(item.get("toString", "")).strip().lower() == target:
            return True
    fields = (payload.get("issue") or {}).get("fields") or {}
    status = (fields.get("status") or {}).get("name")
    return str(status or "").strip().lower() == target


def _issue_number(issue_key: str) -> int:
    match = re.search(r"(\d+)$", issue_key)
    return int(match.group(1)) if match else 0


def _issue_url(issue_key: str) -> str | None:
    if not settings.jira_base_url:
        return None
    return f"{settings.jira_base_url.rstrip('/')}/browse/{issue_key}"


def _jira_issue_body(issue: dict[str, Any]) -> str:
    fields = issue.get("fields") or {}
    parts = [f"Jira issue: {issue.get('key', 'unknown')}"]
    if description := _textify(fields.get("description")):
        parts.append(f"Description:\n{description}")
    if labels := fields.get("labels"):
        parts.append(f"Labels: {', '.join(map(str, labels))}")
    if components := fields.get("components"):
        names = [c.get("name") for c in components if c.get("name")]
        if names:
            parts.append(f"Components: {', '.join(names)}")
    return "\n\n".join(parts)


def _textify(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        return "\n".join(filter(None, (_textify(item) for item in value))).strip()
    if isinstance(value, dict):
        if "text" in value:
            return str(value["text"]).strip()
        return _textify(value.get("content"))
    return str(value).strip()
