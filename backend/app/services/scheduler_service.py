from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, time
from typing import Any

from sqlalchemy.orm import Session
from app.core.database import SessionLocal
from app.models.entities import MigrationSchedule

logger = logging.getLogger(__name__)

_scheduler_task: asyncio.Task | None = None
_is_running: bool = False


def compute_next_run_at(frequency: str, scheduled_time: str) -> datetime:
    """
    Computes the next run datetime in UTC based on frequency and HH:MM string.
    """
    now = datetime.utcnow()
    try:
        parts = scheduled_time.strip().split(":")
        hour = int(parts[0])
        minute = int(parts[1]) if len(parts) > 1 else 0
    except Exception:
        hour, minute = 2, 0

    freq = (frequency or "DAILY").upper()

    if freq == "HOURLY":
        target = now.replace(minute=minute, second=0, microsecond=0)
        if target <= now:
            target += timedelta(hours=1)
        return target
    else:  # DAILY
        target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if target <= now:
            target += timedelta(days=1)
        return target


async def scheduler_worker_loop():
    """
    Background worker loop: polls every 30 seconds for due migration schedules.
    """
    global _is_running
    _is_running = True
    logger.info("Scheduler worker loop started.")

    while _is_running:
        try:
            now = datetime.utcnow()
            with SessionLocal() as db:
                due_schedules = (
                    db.query(MigrationSchedule)
                    .filter(
                        MigrationSchedule.is_enabled == True,
                        MigrationSchedule.next_run_at != None,
                        MigrationSchedule.next_run_at <= now,
                    )
                    .all()
                )

                for schedule in due_schedules:
                    logger.info(
                        f"Triggering scheduled incremental sync for project {schedule.project_id} (scheduled for {schedule.next_run_at})"
                    )
                    schedule.last_run_status = "RUNNING"
                    db.commit()

                    # Execute in background task so one job does not block the polling loop
                    asyncio.create_task(_run_schedule_job(schedule.project_id))

        except Exception as exc:
            logger.error(f"Error in scheduler worker loop: {exc}", exc_info=True)

        await asyncio.sleep(30)


async def _run_schedule_job(project_id: str):
    from app.services.watermark_service import run_incremental_sync_for_project

    with SessionLocal() as db:
        try:
            summary = await run_incremental_sync_for_project(db, project_id, actor="SCHEDULER")
            logger.info(f"Scheduled incremental sync finished for {project_id}: {summary.get('status')}")
        except Exception as e:
            logger.error(f"Exception running scheduled job for {project_id}: {e}", exc_info=True)
            schedule = db.query(MigrationSchedule).filter(MigrationSchedule.project_id == project_id).first()
            if schedule:
                schedule.last_run_status = "FAILED"
                schedule.next_run_at = compute_next_run_at(schedule.frequency, schedule.scheduled_time)
                db.commit()


def start_scheduler():
    global _scheduler_task
    if _scheduler_task is None or _scheduler_task.done():
        _scheduler_task = asyncio.create_task(scheduler_worker_loop())
        logger.info("Background scheduler task initiated.")


def stop_scheduler():
    global _is_running, _scheduler_task
    _is_running = False
    if _scheduler_task and not _scheduler_task.done():
        _scheduler_task.cancel()
        logger.info("Background scheduler task stopped.")
