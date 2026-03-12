from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from web.database import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    # Mark any runs left in running/pending state as failed (server restarted)
    from web.database import SessionLocal
    from web.models import Run
    from datetime import datetime
    db = SessionLocal()
    try:
        stale = db.query(Run).filter(Run.status.in_(["running", "pending"])).all()
        for run in stale:
            run.status = "failed"
            run.error_message = "Server restarted — run was interrupted"
            run.finished_at = datetime.utcnow()
        if stale:
            db.commit()
    finally:
        db.close()
    yield


app = FastAPI(title="Job Finder", lifespan=lifespan)
app.mount("/static", StaticFiles(directory="web/static"), name="static")

from web.routers import auth, profile, runs, jobs, admin, google_drive  # noqa: E402
app.include_router(auth.router)
app.include_router(profile.router)
app.include_router(runs.router)
app.include_router(jobs.router)
app.include_router(admin.router)
app.include_router(google_drive.router)
