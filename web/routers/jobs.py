import io
import zipfile

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy.orm import Session

from web.auth import get_current_user
from web.database import get_db
from web.models import Job, User

router = APIRouter()


@router.get("/jobs")
def list_jobs(
    request: Request,
    min_score: int = 0,
    source: str = "all",
    status: str = "all",
    db: Session = Depends(get_db),
):
    user: User = get_current_user(request, db)
    q = db.query(Job).filter(Job.user_id == user.id)
    if min_score:
        q = q.filter(Job.match_score >= min_score)
    if source != "all":
        q = q.filter(Job.source == source)
    if status != "all":
        q = q.filter(Job.applied_status == status)
    jobs = q.order_by(Job.match_score.desc().nullslast(), Job.created_at.desc()).all()
    return JSONResponse([
        {
            "id": j.id,
            "company": j.company,
            "title": j.title,
            "url": j.url,
            "location": j.location,
            "posted_date": j.posted_date,
            "source": j.source,
            "match_score": j.match_score,
            "match_summary": j.match_summary,
            "has_resume": bool(j.resume_path),
            "has_cover_letter": bool(j.cover_letter_path),
            "resume_drive_url": j.resume_drive_url,
            "cover_letter_drive_url": j.cover_letter_drive_url,
            "applied_status": j.applied_status,
            "created_at": j.created_at.isoformat() if j.created_at else None,
        }
        for j in jobs
    ])


@router.post("/jobs/{job_id}/status")
async def update_status(job_id: int, request: Request, db: Session = Depends(get_db)):
    user: User = get_current_user(request, db)
    body = await request.json()
    new_status = body.get("status", "pending")
    if new_status not in ("pending", "applied", "skipped"):
        return JSONResponse({"error": "Invalid status"}, status_code=400)
    job = db.query(Job).filter(Job.id == job_id, Job.user_id == user.id).first()
    if not job:
        return JSONResponse({"error": "Not found"}, status_code=404)
    job.applied_status = new_status
    db.commit()
    return JSONResponse({"id": job_id, "applied_status": new_status})


@router.get("/jobs/{job_id}/download")
def download_docs(job_id: int, request: Request, db: Session = Depends(get_db)):
    user: User = get_current_user(request, db)
    job = db.query(Job).filter(Job.id == job_id, Job.user_id == user.id).first()
    if not job:
        return JSONResponse({"error": "Not found"}, status_code=404)
    if not job.resume_path and not job.cover_letter_path:
        return JSONResponse({"error": "No tailored documents available for this job."}, status_code=404)

    slug = f"{job.company or 'job'}_{job.title or str(job_id)}"[:60].replace(" ", "_")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        if job.resume_path:
            try:
                zf.write(job.resume_path, f"{slug}_resume.docx")
            except FileNotFoundError:
                pass
        if job.cover_letter_path:
            try:
                zf.write(job.cover_letter_path, f"{slug}_cover_letter.docx")
            except FileNotFoundError:
                pass
    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{slug}_docs.zip"'},
    )
