import threading
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

# Track actively running user run threads (user_id → thread)
_active_runs: dict[int, threading.Thread] = {}


def _run_in_thread(user_id: int, run_id: int) -> None:
    """Execute the pipeline in a background thread with its own DB session."""
    db = SessionLocal()
    try:
        from web.pipeline_runner import run_pipeline_for_user
        run_pipeline_for_user(user_id, run_id, db)
    except Exception as e:
        run = db.get(Run, run_id)
        if run:
            run.status = "failed"
            run.error_message = str(e)
            run.finished_at = datetime.utcnow()
            db.commit()
    finally:
        _active_runs.pop(user_id, None)
        db.close()


@router.post("/runs/trigger")
def trigger_run(request: Request, db: Session = Depends(get_db)):
    user: User = get_current_user(request, db)

    if user.id in _active_runs and _active_runs[user.id].is_alive():
        return JSONResponse({"error": "A run is already in progress."}, status_code=409)

    run = Run(user_id=user.id, status="pending", started_at=datetime.utcnow())
    db.add(run)
    db.commit()
    db.refresh(run)

    t = threading.Thread(target=_run_in_thread, args=(user.id, run.id), daemon=True)
    _active_runs[user.id] = t
    t.start()

    return JSONResponse({"run_id": run.id, "status": "pending"})


@router.get("/runs/{run_id}/status")
def run_status(run_id: int, request: Request, db: Session = Depends(get_db)):
    user: User = get_current_user(request, db)
    run = db.query(Run).filter(Run.id == run_id, Run.user_id == user.id).first()
    if not run:
        return JSONResponse({"error": "Not found"}, status_code=404)
    return JSONResponse({
        "status": run.status,
        "jobs_found": run.jobs_found or 0,
        "jobs_tailored": run.jobs_tailored or 0,
        "error_message": run.error_message,
        "log_tail": (run.log_tail or "")[-2000:],  # last 2000 chars for display
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
