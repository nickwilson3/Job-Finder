import queue as _queue_module
import threading
import time
from datetime import datetime

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from web.auth import get_current_user
from web.database import get_db, SessionLocal
from web.models import Run, User
from web.storage import log_path

router = APIRouter()
templates = Jinja2Templates(directory="web/templates")

# ---------------------------------------------------------------------------
# Global run queue — only ONE pipeline executes at a time (memory safety).
# ---------------------------------------------------------------------------
_run_queue: _queue_module.Queue = _queue_module.Queue()
_cancel_events: dict[int, threading.Event] = {}   # run_id -> Event
_active_run_id: int | None = None                  # run_id currently executing
_worker_started = False
_worker_lock = threading.Lock()


def _ensure_worker():
    global _worker_started
    with _worker_lock:
        if not _worker_started:
            _worker_started = True
            threading.Thread(target=_worker_loop, daemon=True).start()


def _worker_loop():
    global _active_run_id
    while True:
        user_id, run_id = _run_queue.get()
        try:
            ev = _cancel_events.get(run_id)
            if ev and ev.is_set():
                # Cancelled while queued — mark and skip
                db = SessionLocal()
                try:
                    run = db.get(Run, run_id)
                    if run:
                        run.status = "cancelled"
                        run.finished_at = datetime.utcnow()
                        run.status_message = "Cancelled before starting"
                        run.queue_position = 0
                        db.commit()
                finally:
                    db.close()
                continue

            _active_run_id = run_id
            _run_in_thread(user_id, run_id)
        finally:
            _active_run_id = None
            _cancel_events.pop(run_id, None)
            _run_queue.task_done()


def _run_in_thread(user_id: int, run_id: int) -> None:
    """Execute the pipeline synchronously (called from worker thread)."""
    db = SessionLocal()
    try:
        cancel_event = _cancel_events.get(run_id, threading.Event())

        def progress_callback(pct: int, message: str):
            run = db.get(Run, run_id)
            if run:
                run.progress_pct = pct
                run.status_message = message
                db.commit()

        from web.pipeline_runner import run_pipeline_for_user
        run_pipeline_for_user(user_id, run_id, db,
                              cancel_event=cancel_event,
                              progress_callback=progress_callback)
    except Exception as e:
        run = db.get(Run, run_id)
        if run:
            run.status = "failed"
            run.error_message = str(e)
            run.finished_at = datetime.utcnow()
            db.commit()
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.post("/runs/trigger")
def trigger_run(request: Request, db: Session = Depends(get_db)):
    _ensure_worker()
    user: User = get_current_user(request, db)

    # Count how many runs are already pending (queued but not started)
    pending_count = db.query(Run).filter(Run.status == "pending").count()
    queue_position = pending_count + 1  # this run will be at this position

    run = Run(
        user_id=user.id,
        status="pending",
        started_at=datetime.utcnow(),
        queue_position=queue_position,
        status_message="Queued" if pending_count > 0 else "Starting...",
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    cancel_event = threading.Event()
    _cancel_events[run.id] = cancel_event

    _run_queue.put((user.id, run.id))

    return JSONResponse({"run_id": run.id, "status": "pending", "queue_position": queue_position})


@router.post("/runs/{run_id}/cancel")
def cancel_run(run_id: int, request: Request, db: Session = Depends(get_db)):
    user: User = get_current_user(request, db)
    run = db.query(Run).filter(Run.id == run_id, Run.user_id == user.id).first()
    if not run:
        return JSONResponse({"error": "Not found"}, status_code=404)
    if run.status not in ("pending", "running"):
        return JSONResponse({"error": "Run is not active"}, status_code=400)

    ev = _cancel_events.get(run_id)
    if ev:
        ev.set()

    # If it's still pending (queued), mark it cancelled immediately
    if run.status == "pending":
        run.status = "cancelled"
        run.finished_at = datetime.utcnow()
        run.status_message = "Cancelled"
        run.queue_position = 0
        db.commit()

    return JSONResponse({"status": "cancelling"})


@router.get("/runs/{run_id}/status")
def run_status(run_id: int, request: Request, db: Session = Depends(get_db)):
    user: User = get_current_user(request, db)
    run = db.query(Run).filter(Run.id == run_id, Run.user_id == user.id).first()
    if not run:
        return JSONResponse({"error": "Not found"}, status_code=404)

    # Compute live queue position from DB (updates as runs ahead complete)
    queue_position = 0
    if run.status == "pending":
        queue_position = db.query(Run).filter(
            Run.status == "pending",
            Run.id < run.id
        ).count() + 1

    return JSONResponse({
        "status": run.status,
        "jobs_found": run.jobs_found or 0,
        "jobs_tailored": run.jobs_tailored or 0,
        "error_message": run.error_message,
        "log_tail": (run.log_tail or "")[-2000:],
        "progress_pct": run.progress_pct or 0,
        "status_message": run.status_message or "",
        "queue_position": queue_position,
    })


@router.get("/runs/{run_id}/logs", response_class=PlainTextResponse)
def run_logs(run_id: int, request: Request, db: Session = Depends(get_db)):
    user: User = get_current_user(request, db)
    run = db.query(Run).filter(Run.id == run_id, Run.user_id == user.id).first()
    if not run:
        return PlainTextResponse("Run not found.", status_code=404)
    path = log_path(user.id)
    if path.exists():
        return PlainTextResponse(path.read_text(encoding="utf-8"))
    return PlainTextResponse(run.log_tail or "(no log available)")


@router.get("/runs", response_class=HTMLResponse)
def runs_page(request: Request, db: Session = Depends(get_db)):
    user: User = get_current_user(request, db)
    runs = db.query(Run).filter(Run.user_id == user.id).order_by(Run.started_at.desc()).limit(50).all()
    return templates.TemplateResponse(
        "runs.html",
        {"request": request, "user": user, "active": "runs", "runs": runs},
    )
