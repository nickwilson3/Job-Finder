"""
Job Finder — Main Orchestrator

Usage:
    python src/main.py             # Full run
    python src/main.py --dry-run   # Print search params, no API calls
"""

import argparse
import logging
import os
import re
import sys
from datetime import datetime
from pathlib import Path

import anthropic
import yaml
from dotenv import load_dotenv
from docx import Document

# Ensure src/ is on the path when running from project root
sys.path.insert(0, str(Path(__file__).parent))

from search.linkedin import search_linkedin
from search.company_sites import search_company_sites
from analyzer.job_matcher import score_job
from tailor.resume_tailor import tailor_resume
from tailor.cover_letter_tailor import tailor_cover_letter
from reporter.excel_reporter import init_workbook, append_job, get_tracked_urls, get_application_history
from analyzer.preference_learner import build_preference_context


# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------

def setup_logging() -> logging.Logger:
    Path("outputs").mkdir(exist_ok=True)
    fmt = "%(asctime)s  %(levelname)-8s  %(message)s"
    logging.basicConfig(
        level=logging.DEBUG,
        format=fmt,
        handlers=[
            logging.FileHandler("outputs/run.log", encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )
    # Silence noisy third-party loggers
    for lib in ("urllib3", "playwright", "asyncio", "httpx", "httpcore", "anthropic"):
        logging.getLogger(lib).setLevel(logging.WARNING)
    # Google API client is especially noisy (file_cache warnings, per-request DEBUG logs)
    for lib in (
        "googleapiclient", "googleapiclient.discovery",
        "google.auth", "google.auth.transport", "google.auth.transport.requests",
    ):
        logging.getLogger(lib).setLevel(logging.ERROR)
    return logging.getLogger("job_finder")


# ---------------------------------------------------------------------------
# Config / helpers
# ---------------------------------------------------------------------------

def load_config() -> tuple[dict, dict]:
    """Load settings.yaml and criteria.yaml from config/."""
    with open("config/settings.yaml") as f:
        settings = yaml.safe_load(f)
    with open("config/criteria.yaml") as f:
        criteria = yaml.safe_load(f)
    return settings, criteria


def extract_text(docx_path: str) -> str:
    """Extract plain text from a DOCX file."""
    doc = Document(docx_path)
    return "\n".join(p.text for p in doc.paragraphs if p.text.strip())


def safe_slug(text: str) -> str:
    """Convert arbitrary text to a filesystem-safe slug."""
    return re.sub(r"[^\w\-]", "_", text)[:60]


def upload_docs_to_drive(
    job: dict,
    resume_out: str,
    cover_out: str,
    folder_id: str,
    log: logging.Logger,
) -> None:
    """
    Upload tailored DOCX files to Google Drive as native Google Docs.
    Updates job["resume_path"] and job["cover_letter_path"] with Drive URLs.
    Native Google Docs don't consume storage quota (unlike binary uploads).
    No-ops silently if folder_id is empty.
    """
    if not folder_id:
        return
    from reporter.excel_reporter import create_gdoc_from_docx
    company = job.get("company", "")
    title = job.get("title", "")
    slug = f"{company} — {title}"

    try:
        url = create_gdoc_from_docx(resume_out, f"Resume — {slug}", folder_id)
        job["resume_path"] = url
        log.debug(f"    Resume → Drive: {url}")
    except Exception as e:
        log.warning(f"    Resume Drive upload failed: {e}")

    try:
        url = create_gdoc_from_docx(cover_out, f"Cover Letter — {slug}", folder_id)
        job["cover_letter_path"] = url
        log.debug(f"    Cover letter → Drive: {url}")
    except Exception as e:
        log.warning(f"    Cover letter Drive upload failed: {e}")


# ---------------------------------------------------------------------------
# Dry run
# ---------------------------------------------------------------------------

def dry_run(settings: dict, criteria: dict) -> None:
    print("\n=== Job Finder - Dry Run ===\n")
    print(f"Cities:        {settings['cities']}")
    print(f"Job Titles:    {settings['job_titles']}")
    print(f"Keywords:      {settings['keywords']}")
    print(f"Exclude:       {settings.get('exclude_keywords', [])}")
    print(f"Remote OK:     {settings['filters']['remote_options']}")
    print(f"Min Score:     {settings['filters']['min_match_score']}")
    print(f"Sources:       {[k for k, v in settings['sources'].items() if v]}")
    print(f"\nSheet ID:      {settings['output'].get('google_sheet_id', '(not set)')}")
    print(f"Applications:  {settings['output']['applications_dir']}")
    print("\nDry run complete. Edit config/settings.yaml to adjust settings.\n")


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Job Finder Agent")
    parser.add_argument("--dry-run", action="store_true", help="Print config only, no API calls")
    args = parser.parse_args()

    load_dotenv()
    settings, criteria = load_config()

    if args.dry_run:
        dry_run(settings, criteria)
        return

    log = setup_logging()
    log.info("Job Finder starting")

    # Validate environment
    if not os.getenv("ANTHROPIC_API_KEY"):
        log.error("ANTHROPIC_API_KEY not set. Copy .env.example to .env and add your key.")
        sys.exit(1)

    for f in ["inputs/resume.docx", "inputs/cover_letter.docx"]:
        if not os.path.exists(f):
            log.error(f"Missing required input file: {f}")
            sys.exit(1)

    client = anthropic.Anthropic()

    cities = settings["cities"]
    titles = settings["job_titles"]
    keywords = settings["keywords"]
    filters = settings["filters"]
    sources = settings["sources"]
    sheet_id = settings["output"].get("google_sheet_id", "")
    drive_folder_id = settings["output"].get("drive_output_folder_id", "")
    apps_dir = settings["output"]["applications_dir"]

    if not sheet_id:
        log.error("google_sheet_id not set in config/settings.yaml — add your Sheet ID to the output section.")
        sys.exit(1)

    deal_breakers = (criteria.get("requirements") or {}).get("deal_breakers", [])
    min_score = criteria.get("min_score_to_tailor", 70)
    strong_threshold = criteria.get("strong_match_threshold", 85)

    # Stats counters
    stats = {
        "found": 0,
        "duplicate_search": 0,   # duplicate within this run's search results
        "duplicate_tracker": 0,  # already in the Excel tracker from a prior run
        "capped": 0,             # deferred because max_jobs_per_run was hit
        "deal_breaker": 0,
        "scored": 0,
        "tailored": 0,
        "error": 0,
    }

    # --- Search ---
    all_jobs: list[dict] = []

    if sources.get("linkedin"):
        log.info("Searching LinkedIn...")
        try:
            found = search_linkedin(cities, titles, keywords, filters)
            log.info(f"  LinkedIn: {len(found)} jobs")
            all_jobs.extend(found)
        except NotImplementedError:
            log.warning("  LinkedIn search not yet implemented, skipping.")

    if sources.get("company_sites"):
        log.info("Searching company sites (Greenhouse + Lever)...")
        # Count company frequency — more appearances = more actively hiring
        from collections import Counter
        company_counts = Counter(
            j["company"] for j in all_jobs
            if j.get("source") == "linkedin" and j.get("company", "Unknown") != "Unknown"
        )
        max_companies = settings.get("max_companies_to_check", 100)
        linkedin_companies = [name for name, _ in company_counts.most_common(max_companies)]
        log.info(f"  Checking top {len(linkedin_companies)} companies on Greenhouse + Lever...")
        try:
            found = search_company_sites(linkedin_companies, titles, keywords, filters)
            log.info(f"  Company sites: {len(found)} jobs")
            all_jobs.extend(found)
        except NotImplementedError:
            log.warning("  Company site search not yet implemented, skipping.")

    if not all_jobs:
        log.warning("No jobs found across all sources.")
        sys.exit(0)

    # Deduplicate within this run's results
    seen: set[str] = set()
    unique_jobs: list[dict] = []
    for job in all_jobs:
        url = job.get("url", "")
        if url and url not in seen:
            seen.add(url)
            unique_jobs.append(job)
        else:
            stats["duplicate_search"] += 1

    stats["found"] = len(unique_jobs)
    log.info(f"Unique jobs this run: {stats['found']}  (duplicates dropped: {stats['duplicate_search']})")

    # Deduplicate against existing tracker + load application history for RL
    init_workbook(sheet_id)
    tracked_urls = get_tracked_urls(sheet_id)
    applied_history, skipped_history = get_application_history(sheet_id)
    preference_context = build_preference_context(applied_history, skipped_history, client)
    if preference_context:
        log.info(f"Preference context learned from {len(applied_history)} applied + {len(skipped_history)} skipped decisions.")
        log.info(f"  Profile: {preference_context}")
    else:
        log.info(f"No preference context yet ({len(applied_history) + len(skipped_history)} decisions — need 5 to activate).")
    new_jobs = [j for j in unique_jobs if j.get("url", "") not in tracked_urls]
    stats["duplicate_tracker"] = len(unique_jobs) - len(new_jobs)

    if stats["duplicate_tracker"]:
        log.info(f"Skipping {stats['duplicate_tracker']} jobs already in tracker.")

    if not new_jobs:
        log.info("No new jobs to process. Tracker is up to date.")
        _print_summary(stats, sheet_id)
        return

    # Sort by posting date (most recent first) so the cap keeps the freshest jobs
    new_jobs.sort(key=lambda j: j.get("posted_date", "") or "", reverse=True)

    # Cap to max_jobs_per_run
    max_jobs = settings.get("max_jobs_per_run", 50)
    if len(new_jobs) > max_jobs:
        stats["capped"] = len(new_jobs) - max_jobs
        log.info(f"Capping to {max_jobs} jobs this run ({stats['capped']} deferred — run again for more).")
        new_jobs = new_jobs[:max_jobs]

    # Enrich LinkedIn jobs with full descriptions (single browser session)
    if sources.get("linkedin") and any(j.get("source") == "linkedin" for j in new_jobs):
        from search.linkedin import fetch_descriptions_batch
        log.info(f"Fetching LinkedIn descriptions for {len(new_jobs)} jobs...")
        fetch_descriptions_batch(new_jobs)

    log.info(f"Processing {len(new_jobs)} new jobs...\n")

    resume_text = extract_text("inputs/resume.docx")
    today = datetime.now().strftime("%Y-%m-%d")

    # --- Score, tailor, track ---
    for job in new_jobs:
        company = job.get("company", "Unknown")
        title = job.get("title", "Unknown")
        source = job.get("source", "")

        # Hard filter: deal-breakers
        desc_lower = job.get("description", "").lower()
        if any(db.lower() in desc_lower for db in deal_breakers):
            log.info(f"  [deal-breaker] {company} — {title}")
            stats["deal_breaker"] += 1
            continue

        # Score with Claude
        log.info(f"  Scoring [{source}]: {company} — {title}")
        try:
            job = score_job(job, resume_text, criteria, client, preference_context=preference_context)
            stats["scored"] += 1
        except Exception as e:
            err_str = str(e)
            log.error(f"    Scoring error: {err_str}")
            stats["error"] += 1
            # Fatal API errors (billing, auth) — no point retrying the rest
            if "credit balance is too low" in err_str or "invalid_api_key" in err_str:
                log.error("  Fatal API error — stopping run. Add credits at console.anthropic.com/settings/billing")
                break
            continue

        score = job.get("match_score") or 0
        flag = "  *** STRONG MATCH ***" if score >= strong_threshold else ""
        log.info(f"    Score: {score}{flag}")

        job["date_found"] = today

        # Tailor docs if above threshold
        if score >= min_score:
            slug = f"{safe_slug(company)}_{safe_slug(title)}"
            job_dir = os.path.join(apps_dir, slug)
            os.makedirs(job_dir, exist_ok=True)

            resume_out = os.path.join(job_dir, "resume.docx")
            cover_out = os.path.join(job_dir, "cover_letter.docx")

            try:
                tailor_resume(job, "inputs/resume.docx", resume_out, client)
                tailor_cover_letter(job, "inputs/cover_letter.docx", cover_out, client, resume_text=resume_text)
                job["resume_path"] = resume_out
                job["cover_letter_path"] = cover_out
                stats["tailored"] += 1
                log.info(f"    Tailored docs -> {job_dir}")

                # Upload to Google Drive as native Google Docs (quota-free)
                upload_docs_to_drive(job, resume_out, cover_out, drive_folder_id, log)
            except Exception as e:
                log.error(f"    Tailoring error: {e}")
                stats["error"] += 1

        append_job(sheet_id, job)

    _print_summary(stats, sheet_id)
    log.info("Run complete.")


def _print_summary(stats: dict, sheet_id: str) -> None:
    log = logging.getLogger("job_finder")
    log.info("")
    log.info("=" * 45)
    log.info("  RUN SUMMARY")
    log.info("=" * 45)
    log.info(f"  Jobs found (new):      {stats['found']}")
    log.info(f"  Already in tracker:    {stats['duplicate_tracker']}")
    log.info(f"  Deferred (cap):        {stats['capped']}")
    log.info(f"  Deal-breaker skipped:  {stats['deal_breaker']}")
    log.info(f"  Scored by Claude:      {stats['scored']}")
    log.info(f"  Applications tailored: {stats['tailored']}")
    log.info(f"  Errors:                {stats['error']}")
    log.info(f"  Tracker:               {sheet_id}")
    log.info("=" * 45)


if __name__ == "__main__":
    main()
