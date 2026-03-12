"""APScheduler setup for per-user daily pipeline runs."""
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.triggers.cron import CronTrigger

from web.database import DB_PATH

_scheduler: BackgroundScheduler | None = None


def _get_scheduler() -> BackgroundScheduler:
    global _scheduler
    if _scheduler is None:
        jobstore_url = f"sqlite:///{DB_PATH}"
        _scheduler = BackgroundScheduler(
            jobstores={"default": SQLAlchemyJobStore(url=jobstore_url, tablename="apscheduler_jobs")},
            timezone="UTC",
        )
    return _scheduler


def start_scheduler() -> None:
    _get_scheduler().start()


def stop_scheduler() -> None:
    s = _get_scheduler()
    if s.running:
        s.shutdown(wait=False)


def restore_schedules() -> None:
    """Re-register scheduled jobs for all users with schedule_enabled=True on server startup."""
    from web.database import SessionLocal
    from web.models import User
    db = SessionLocal()
    try:
        users = db.query(User).filter(User.schedule_enabled == True, User.is_active == True).all()  # noqa: E712
        for user in users:
            schedule_user_run(user.id, user.schedule_time or "08:00")
    finally:
        db.close()


def _trigger_scheduled_run(user_id: int) -> None:
    """Called by APScheduler — creates a Run record and kicks off the pipeline."""
    from datetime import datetime
    from web.database import SessionLocal
    from web.models import Run
    import threading

    db = SessionLocal()
    try:
        run = Run(user_id=user_id, status="pending", started_at=datetime.utcnow())
        db.add(run)
        db.commit()
        db.refresh(run)
        run_id = run.id
    finally:
        db.close()

    def _run():
        from web.database import SessionLocal as SL
        inner_db = SL()
        try:
            from web.pipeline_runner import run_pipeline_for_user
            run_pipeline_for_user(user_id, run_id, inner_db)
        finally:
            inner_db.close()

    threading.Thread(target=_run, daemon=True).start()


def schedule_user_run(user_id: int, time_str: str) -> None:
    """Add or replace a daily cron job for user_id at HH:MM UTC."""
    hour, minute = (time_str or "08:00").split(":")
    _get_scheduler().add_job(
        func=_trigger_scheduled_run,
        trigger=CronTrigger(hour=int(hour), minute=int(minute), timezone="UTC"),
        id=f"user_{user_id}_daily",
        replace_existing=True,
        args=[user_id],
    )


def remove_user_schedule(user_id: int) -> None:
    job_id = f"user_{user_id}_daily"
    s = _get_scheduler()
    if s.get_job(job_id):
        s.remove_job(job_id)
