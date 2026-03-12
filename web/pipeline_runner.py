"""
Per-user pipeline orchestration.

Wraps the existing src/ modules for multi-user web execution.
Each user gets their own file directories and config; results are stored in SQLite.
Nick's CLI (src/main.py) is completely separate and unchanged.
"""
import logging
import os
import re
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

import anthropic
from docx import Document

# Ensure src/ is importable
_SRC = Path(__file__).parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from search.linkedin import search_linkedin
from search.company_sites import search_company_sites
from analyzer.job_matcher import score_job
from analyzer.preference_learner import build_preference_context
from tailor.resume_tailor import tailor_resume
from tailor.cover_letter_tailor import tailor_cover_letter

from web.storage import log_path, outputs_dir, read_criteria, read_settings
from web.drive_uploader import upload_to_user_drive

# ---------------------------------------------------------------------------
# Shared Anthropic client (centralized key — all users share Nick's account)
# ---------------------------------------------------------------------------

def _get_client() -> anthropic.Anthropic:
    from dotenv import load_dotenv
    load_dotenv()
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        raise RuntimeError("ANTHROPIC_API_KEY not set in .env")
    return anthropic.Anthropic(api_key=key)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _extract_text(docx_path: str) -> str:
    doc = Document(docx_path)
    return "\n".join(p.text for p in doc.paragraphs if p.text.strip())


def _safe_slug(text: str) -> str:
    return re.sub(r"[^\w\-]", "_", text)[:60]


def _setup_run_logger(user_id: int) -> logging.Logger:
    log_file = log_path(user_id)
    log_file.parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger(f"job_finder.user_{user_id}")
    logger.setLevel(logging.DEBUG)
    logger.handlers.clear()
    fh = logging.FileHandler(log_file, encoding="utf-8", mode="w")
    fh.setFormatter(logging.Formatter("%(asctime)s  %(levelname)-8s  %(message)s"))
    logger.addHandler(fh)
    for lib in ("urllib3", "playwright", "asyncio", "httpx", "httpcore", "anthropic"):
        logging.getLogger(lib).setLevel(logging.WARNING)
    return logger


def _get_log_tail(user_id: int, lines: int = 100) -> str:
    path = log_path(user_id)
    if not path.exists():
        return ""
    with open(path, encoding="utf-8") as f:
        return "".join(f.readlines()[-lines:])


# ---------------------------------------------------------------------------
# Application history from SQLite (replaces Google Sheets RL read)
# ---------------------------------------------------------------------------

def _load_history(db, user_id: int) -> tuple[list[dict], list[dict]]:
    from web.models import Job
    rows = db.query(Job).filter(Job.user_id == user_id).all()
    applied, skipped = [], []
    for row in rows:
        entry = {
            "company": row.company or "",
            "title": row.title or "",
            "match_summary": row.match_summary or "",
        }
        if row.applied_status == "applied":
            applied.append(entry)
        elif row.applied_status == "skipped":
            skipped.append(entry)
    return applied, skipped


def _get_seen_urls(db, user_id: int) -> set[str]:
    from web.models import Job
    rows = db.query(Job.url).filter(Job.user_id == user_id, Job.url.isnot(None)).all()
    return {r.url for r in rows}


# ---------------------------------------------------------------------------
# Main per-user pipeline entry point
# ---------------------------------------------------------------------------

def run_pipeline_for_user(user_id: int, run_id: int, db, cancel_event=None, progress_callback=None) -> None:
    """
    Execute the full job-finding pipeline for a single user.
    Updates the Run record in DB as it progresses.
    All results are written to the jobs table (not Google Sheets).
    """
    from web.models import Run, Job

    log = _setup_run_logger(user_id)
    run: Run = db.get(Run, run_id)

    def _update_run(**kwargs):
        for k, v in kwargs.items():
            setattr(run, k, v)
        db.commit()

    _update_run(status="running")
    import threading as _threading
    if cancel_event is None:
        cancel_event = _threading.Event()
    if progress_callback is None:
        progress_callback = lambda pct, msg: None

    progress_callback(5, "Searching LinkedIn...")
    log.info(f"Job Finder starting for user {user_id}")

    try:
        settings = read_settings(user_id)
        criteria = read_criteria(user_id)
    except Exception as e:
        log.error(f"Failed to load config: {e}")
        _update_run(status="failed", error_message=str(e), finished_at=datetime.utcnow(), log_tail=_get_log_tail(user_id))
        return

    from web.storage import inputs_dir
    idir = inputs_dir(user_id)
    resume_path = str(idir / "resume.docx")
    cover_path = str(idir / "cover_letter.docx")

    if not Path(resume_path).exists() or not Path(cover_path).exists():
        msg = "Resume or cover letter not uploaded. Go to Settings to upload your documents."
        log.error(msg)
        _update_run(status="failed", error_message=msg, finished_at=datetime.utcnow(), log_tail=_get_log_tail(user_id))
        return

    try:
        client = _get_client()
    except RuntimeError as e:
        log.error(str(e))
        _update_run(status="failed", error_message=str(e), finished_at=datetime.utcnow(), log_tail=_get_log_tail(user_id))
        return

    cities = settings.get("cities", [])
    titles = settings.get("job_titles", [])
    keywords = settings.get("keywords", [])
    filters = settings.get("filters", {})
    sources = settings.get("sources", {"linkedin": True, "company_sites": True})
    max_jobs = settings.get("max_jobs_per_run", 50)
    max_companies = settings.get("max_companies_to_check", 100)

    deal_breakers = (criteria.get("requirements") or {}).get("deal_breakers", [])
    min_score = criteria.get("min_score_to_tailor", 50)
    strong_threshold = criteria.get("strong_match_threshold", 85)

    all_jobs: list[dict] = []

    # --- Search ---
    # Pre-load seen URLs so the description_filter_fn can dedup+cap inside the search browser.
    # This merges the LinkedIn search + description fetch into ONE Chromium launch,
    # halving peak memory usage on Render's 512 MB free tier.
    seen_urls_for_filter = _get_seen_urls(db, user_id)

    def _description_filter(scraped_jobs: list[dict]) -> list[dict]:
        """Dedup + cap within the still-open search browser session."""
        if cancel_event.is_set():
            return []
        progress_callback(25, "Fetching job descriptions...")
        seen: set[str] = set()
        unique: list[dict] = []
        for j in scraped_jobs:
            url = j.get("url", "")
            if url and url not in seen:
                seen.add(url)
                unique.append(j)
        new = [j for j in unique if j.get("url", "") not in seen_urls_for_filter]
        new.sort(key=lambda j: j.get("posted_date", "") or "", reverse=True)
        return new[:max_jobs]

    if sources.get("linkedin"):
        log.info("Searching LinkedIn...")
        try:
            # Uses shared inputs/linkedin_session.json (Nick's dummy account).
            # description_filter_fn fetches descriptions in the same browser session —
            # no second Chromium launch needed.
            found = search_linkedin(
                cities, titles, keywords, filters,
                description_filter_fn=_description_filter,
            )
            log.info(f"  LinkedIn: {len(found)} jobs")
            all_jobs.extend(found)
        except Exception as e:
            log.warning(f"  LinkedIn search error: {e}")

    if sources.get("company_sites"):
        log.info("Searching company sites (Greenhouse + Lever)...")
        company_counts = Counter(
            j["company"] for j in all_jobs
            if j.get("source") == "linkedin" and j.get("company", "Unknown") != "Unknown"
        )
        linkedin_companies = [name for name, _ in company_counts.most_common(max_companies)]
        try:
            found = search_company_sites(linkedin_companies, titles, keywords, filters)
            log.info(f"  Company sites: {len(found)} jobs")
            all_jobs.extend(found)
        except Exception as e:
            log.warning(f"  Company sites error: {e}")

    if not all_jobs:
        log.warning("No jobs found.")
        _update_run(status="complete", jobs_found=0, finished_at=datetime.utcnow(), log_tail=_get_log_tail(user_id))
        return

    # Dedup within run
    seen: set[str] = set()
    unique_jobs: list[dict] = []
    for job in all_jobs:
        url = job.get("url", "")
        if url and url not in seen:
            seen.add(url)
            unique_jobs.append(job)

    # Dedup against DB history for this user
    seen_urls = _get_seen_urls(db, user_id)
    new_jobs = [j for j in unique_jobs if j.get("url", "") not in seen_urls]
    log.info(f"New jobs after dedup: {len(new_jobs)} (already seen: {len(unique_jobs) - len(new_jobs)})")

    if not new_jobs:
        log.info("No new jobs to process.")
        _update_run(status="complete", jobs_found=0, finished_at=datetime.utcnow(), log_tail=_get_log_tail(user_id))
        return

    if cancel_event.is_set():
        log.info("Run cancelled by user.")
        _update_run(status="cancelled", finished_at=datetime.utcnow(), log_tail=_get_log_tail(user_id), status_message="Cancelled")
        return

    # RL: load application history
    applied_hist, skipped_hist = _load_history(db, user_id)
    preference_context = build_preference_context(applied_hist, skipped_hist, client)
    if preference_context:
        log.info(f"Preference profile active ({len(applied_hist)} applied / {len(skipped_hist)} skipped): {preference_context}")

    # Sort by posting date (freshest first), cap
    new_jobs.sort(key=lambda j: j.get("posted_date", "") or "", reverse=True)
    if len(new_jobs) > max_jobs:
        log.info(f"Capping to {max_jobs} jobs ({len(new_jobs) - max_jobs} deferred).")
        new_jobs = new_jobs[:max_jobs]

    progress_callback(45, f"Scoring {len(new_jobs)} jobs...")

    # LinkedIn descriptions were already fetched during the search browser session above.
    log.info(f"Processing {len(new_jobs)} new jobs...\n")
    resume_text = _extract_text(resume_path)
    today = datetime.utcnow().strftime("%Y-%m-%d")
    user_apps_dir = outputs_dir(user_id) / "applications"
    user_apps_dir.mkdir(parents=True, exist_ok=True)

    tailored_count = 0

    # Load user's Drive state once before the loop
    from web.models import User as UserModel
    user_obj: UserModel = db.get(UserModel, user_id)
    drive_connected = user_obj.google_drive_connected if user_obj else False
    cached_folder_id = user_obj.google_drive_folder_id if user_obj else None

    for job in new_jobs:
        if cancel_event.is_set():
            log.info("Run cancelled by user.")
            _update_run(status="cancelled", finished_at=datetime.utcnow(), log_tail=_get_log_tail(user_id), status_message="Cancelled")
            return

        company = job.get("company", "Unknown")
        title = job.get("title", "Unknown")
        source_tag = job.get("source", "")

        # Deal-breaker filter
        desc_lower = job.get("description", "").lower()
        if any(db_kw.lower() in desc_lower for db_kw in deal_breakers):
            log.info(f"  [deal-breaker] {company} — {title}")
            continue

        log.info(f"  Scoring [{source_tag}]: {company} — {title}")
        try:
            job = score_job(job, resume_text, criteria, client, preference_context=preference_context)
        except Exception as e:
            err_str = str(e)
            log.error(f"    Scoring error: {err_str}")
            if "credit balance is too low" in err_str or "invalid_api_key" in err_str:
                log.error("  Fatal API error — stopping run.")
                break
            continue

        score = job.get("match_score") or 0
        log.info(f"    Score: {score}{'  *** STRONG MATCH ***' if score >= strong_threshold else ''}")
        job["date_found"] = today

        resume_out_path = None
        cover_out_path = None

        if score >= min_score:
            slug = f"{_safe_slug(company)}_{_safe_slug(title)}"
            job_dir = user_apps_dir / slug
            job_dir.mkdir(parents=True, exist_ok=True)
            resume_out_path = str(job_dir / "resume.docx")
            cover_out_path = str(job_dir / "cover_letter.docx")
            try:
                job_index = new_jobs.index(job) + 1
                tailor_pct = 55 + int((job_index / len(new_jobs)) * 30)
                progress_callback(tailor_pct, f"Tailoring documents ({job_index}/{len(new_jobs)})...")
                tailor_resume(job, resume_path, resume_out_path, client)
                tailor_cover_letter(job, cover_path, cover_out_path, client, resume_text=resume_text)
                tailored_count += 1
                log.info(f"    Tailored docs → {job_dir}")
            except Exception as e:
                log.error(f"    Tailoring error: {e}")
                resume_out_path = None
                cover_out_path = None

        # Upload to Google Drive if the user has it connected
        resume_drive_url = None
        cover_drive_url = None
        progress_callback(88, "Uploading to Google Drive...")
        if drive_connected and resume_out_path and cover_out_path:
            slug = f"{_safe_slug(company)}_{_safe_slug(title)}"
            try:
                resume_drive_url, folder_id = upload_to_user_drive(
                    user_id, resume_out_path, f"{slug} — Resume", cached_folder_id
                )
                cached_folder_id = folder_id
                cover_drive_url, _ = upload_to_user_drive(
                    user_id, cover_out_path, f"{slug} — Cover Letter", folder_id
                )
                # Persist folder ID back to user record
                user_obj.google_drive_folder_id = folder_id
                db.commit()
                log.info(f"    Uploaded to Google Drive: {resume_drive_url}")
            except Exception as e:
                log.warning(f"    Drive upload failed: {e}")

        # Insert into DB
        db_job = Job(
            user_id=user_id,
            run_id=run_id,
            company=company,
            title=title,
            url=job.get("url"),
            location=job.get("location"),
            posted_date=job.get("posted_date"),
            source=source_tag,
            match_score=score,
            match_summary=job.get("match_summary"),
            resume_path=resume_out_path,
            cover_letter_path=cover_out_path,
            resume_drive_url=resume_drive_url,
            cover_letter_drive_url=cover_drive_url,
            applied_status="pending",
            created_at=datetime.utcnow(),
        )
        db.add(db_job)
        db.commit()

    log_tail = _get_log_tail(user_id)
    _update_run(
        status="complete",
        jobs_found=len(new_jobs),
        jobs_tailored=tailored_count,
        finished_at=datetime.utcnow(),
        log_tail=log_tail,
        progress_pct=100,
        status_message=f"Complete — {len(new_jobs)} jobs found, {tailored_count} tailored",
    )
    log.info(f"Run complete. {len(new_jobs)} processed, {tailored_count} tailored.")
