import shutil
from pathlib import Path

from fastapi import APIRouter, Depends, Form, Request, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from web.auth import get_current_user
from web.database import get_db
from web.models import User
from web.storage import (
    google_token_path,
    inputs_dir,
    read_criteria,
    read_settings,
    write_criteria,
    write_settings,
)

router = APIRouter()
templates = Jinja2Templates(directory="web/templates")


def _parse_list(value: str) -> list[str]:
    """Split a comma-or-newline separated string into a cleaned list."""
    sep = "\n" if "\n" in value else ","
    return [v.strip() for v in value.split(sep) if v.strip()]


@router.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request, db: Session = Depends(get_db)):
    user: User = get_current_user(request, db)
    return templates.TemplateResponse(
        "dashboard.html", {"request": request, "user": user, "active": "dashboard"}
    )


@router.get("/settings", response_class=HTMLResponse)
def settings_page(request: Request, db: Session = Depends(get_db)):
    user: User = get_current_user(request, db)
    settings = read_settings(user.id)
    criteria = read_criteria(user.id)
    idir = inputs_dir(user.id)
    has_resume = (idir / "resume.docx").exists()
    has_cl = (idir / "cover_letter.docx").exists()
    # Check actual token file on disk — DB flag can be stale after a redeploy
    drive_connected = google_token_path(user.id).exists()
    # Sync DB if they've drifted (token gone after redeploy)
    if user.google_drive_connected and not drive_connected:
        user.google_drive_connected = False
        from web.database import SessionLocal
        db.commit()
    return templates.TemplateResponse(
        "settings.html",
        {
            "request": request,
            "user": user,
            "active": "settings",
            "settings": settings,
            "criteria": criteria,
            "has_resume": has_resume,
            "has_cl": has_cl,
            "drive_connected": drive_connected,
            "success": request.query_params.get("saved"),
        },
    )


@router.post("/settings/files")
async def upload_files(
    request: Request,
    resume: UploadFile = File(None),
    cover_letter: UploadFile = File(None),
    db: Session = Depends(get_db),
):
    user: User = get_current_user(request, db)
    idir = inputs_dir(user.id)
    idir.mkdir(parents=True, exist_ok=True)
    if resume and resume.filename:
        dest = idir / "resume.docx"
        with open(dest, "wb") as f:
            shutil.copyfileobj(resume.file, f)
    if cover_letter and cover_letter.filename:
        dest = idir / "cover_letter.docx"
        with open(dest, "wb") as f:
            shutil.copyfileobj(cover_letter.file, f)
    return RedirectResponse("/settings?saved=1", status_code=302)


@router.post("/settings/search")
def save_search(
    request: Request,
    cities: str = Form(""),
    job_titles: str = Form(""),
    keywords: str = Form(""),
    exclude_keywords: str = Form(""),
    employment_type: str = Form("full-time"),
    remote_options: list[str] = Form(["remote", "hybrid", "on-site"]),
    posted_within_days: int = Form(30),
    max_jobs_per_run: int = Form(50),
    db: Session = Depends(get_db),
):
    user: User = get_current_user(request, db)
    settings = read_settings(user.id)
    settings["cities"] = _parse_list(cities)
    settings["job_titles"] = _parse_list(job_titles)
    settings["keywords"] = _parse_list(keywords)
    settings["exclude_keywords"] = _parse_list(exclude_keywords)
    settings["filters"]["employment_type"] = employment_type
    settings["filters"]["remote_options"] = remote_options
    settings["filters"]["posted_within_days"] = posted_within_days
    settings["max_jobs_per_run"] = max_jobs_per_run
    write_settings(user.id, settings)
    return RedirectResponse("/settings?saved=1", status_code=302)


@router.post("/settings/criteria")
def save_criteria(
    request: Request,
    candidate_name: str = Form(""),
    target_titles: str = Form(""),
    years_of_experience: int = Form(0),
    experience_level: str = Form("Entry"),
    strong_skills: str = Form(""),
    familiar_skills: str = Form(""),
    industries: str = Form(""),
    soft_skills: str = Form(""),
    deal_breakers: str = Form(""),
    min_score_to_tailor: int = Form(50),
    weight_skills: int = Form(40),
    weight_experience: int = Form(20),
    weight_title: int = Form(20),
    weight_industry: int = Form(10),
    weight_location: int = Form(10),
    db: Session = Depends(get_db),
):
    user: User = get_current_user(request, db)
    criteria = read_criteria(user.id)
    criteria["candidate"]["name"] = candidate_name
    criteria["candidate"]["target_titles"] = _parse_list(target_titles)
    criteria["candidate"]["years_of_experience"] = years_of_experience
    criteria["candidate"]["experience_level"] = experience_level
    criteria["candidate"]["skills"]["strong"] = _parse_list(strong_skills)
    criteria["candidate"]["skills"]["familiar"] = _parse_list(familiar_skills)
    criteria["candidate"]["industries"] = _parse_list(industries)
    criteria["candidate"]["soft_skills"] = _parse_list(soft_skills)
    criteria["requirements"]["deal_breakers"] = _parse_list(deal_breakers)
    criteria["min_score_to_tailor"] = min_score_to_tailor
    criteria["scoring_weights"] = {
        "skills_match": weight_skills,
        "experience_level": weight_experience,
        "title_alignment": weight_title,
        "industry_fit": weight_industry,
        "location_fit": weight_location,
    }
    # Keep location in sync with search settings
    s = read_settings(user.id)
    criteria["location"]["preferred_cities"] = s.get("cities", [])
    write_criteria(user.id, criteria)
    return RedirectResponse("/settings?saved=1", status_code=302)


