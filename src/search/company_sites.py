# Company sites scraper
# Queries Greenhouse and Lever public ATS APIs directly — no API key required.
# Company slugs are auto-derived from LinkedIn results passed in at runtime.

import re
import time

import requests
from bs4 import BeautifulSoup

GREENHOUSE_API = "https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true"
LEVER_API = "https://api.lever.co/v0/postings/{slug}?mode=json&content=true"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}


def company_to_slug(name: str) -> str:
    """Convert a company display name to a likely ATS URL slug."""
    slug = name.lower()
    # Remove common corporate suffixes
    slug = re.sub(
        r"\b(inc|llc|corp|co|ltd|limited|group|holdings|technologies|solutions|labs|studio|studios)\b\.?",
        "",
        slug,
    )
    # Replace non-alphanumeric runs with a single hyphen
    slug = re.sub(r"[^a-z0-9]+", "-", slug).strip("-")
    return slug


def _strip_html(html: str) -> str:
    """Strip HTML tags and return plain text, truncated to 3000 chars."""
    text = BeautifulSoup(html, "html.parser").get_text(separator=" ")
    return " ".join(text.split())[:3000]


def _title_matches(job_title: str, target_titles: list[str]) -> bool:
    """Return True if the job title contains any of the target title keywords."""
    job_lower = job_title.lower()
    return any(t.lower() in job_lower for t in target_titles)


def _query_greenhouse(slug: str, titles: list[str], original_name: str) -> list[dict]:
    """Query a company's Greenhouse job board and return matching jobs."""
    url = GREENHOUSE_API.format(slug=slug)
    try:
        resp = requests.get(url, headers=HEADERS, timeout=10)
        if resp.status_code == 404:
            return []
        resp.raise_for_status()
        data = resp.json()
    except Exception:
        return []

    jobs = []
    for item in data.get("jobs", []):
        title = item.get("title", "")
        if not _title_matches(title, titles):
            continue
        loc_data = item.get("location") or {}
        location = loc_data.get("name", "") if isinstance(loc_data, dict) else str(loc_data)
        description = _strip_html(item.get("content", ""))
        jobs.append({
            "company": original_name,
            "title": title,
            "description": description,
            "url": item.get("absolute_url", ""),
            "location": location,
            "posted_date": item.get("updated_at", ""),
            "source": "company_site",
        })
    return jobs


def _query_lever(slug: str, titles: list[str], original_name: str) -> list[dict]:
    """Query a company's Lever job board and return matching jobs."""
    url = LEVER_API.format(slug=slug)
    try:
        resp = requests.get(url, headers=HEADERS, timeout=10)
        if resp.status_code == 404:
            return []
        resp.raise_for_status()
        data = resp.json()
    except Exception:
        return []

    jobs = []
    for item in data:
        title = item.get("text", "")
        if not _title_matches(title, titles):
            continue
        categories = item.get("categories") or {}
        location = categories.get("location", "") if isinstance(categories, dict) else ""
        description = item.get("descriptionPlain", "") or _strip_html(item.get("description", ""))

        # createdAt is Unix timestamp in milliseconds
        created_ms = item.get("createdAt", 0)
        if created_ms:
            from datetime import datetime, timezone
            posted_date = datetime.fromtimestamp(created_ms / 1000, tz=timezone.utc).isoformat()
        else:
            posted_date = ""

        jobs.append({
            "company": original_name,
            "title": title,
            "description": description[:3000],
            "url": item.get("hostedUrl", ""),
            "location": location,
            "posted_date": posted_date,
            "source": "company_site",
        })
    return jobs


def search_company_sites(
    companies: list[str],
    titles: list[str],
    keywords: list[str],
    filters: dict,
) -> list[dict]:
    """
    Search Greenhouse and Lever ATS APIs for jobs at the given companies.
    Companies are derived from LinkedIn results — no manual config needed.

    Returns: [{"company", "title", "description", "url", "location", "posted_date", "source"}]
    """
    if not companies:
        return []

    # Deduplicate slugs while preserving original display name
    seen_slugs: set[str] = set()
    slugs: list[tuple[str, str]] = []  # (slug, original_name)
    for name in companies:
        slug = company_to_slug(name)
        if slug and slug not in seen_slugs:
            seen_slugs.add(slug)
            slugs.append((slug, name))

    all_jobs: list[dict] = []
    seen_urls: set[str] = set()

    for slug, original_name in slugs:
        # Try Greenhouse
        for job in _query_greenhouse(slug, titles, original_name):
            if job["url"] and job["url"] not in seen_urls:
                seen_urls.add(job["url"])
                all_jobs.append(job)
        time.sleep(0.5)

        # Try Lever
        for job in _query_lever(slug, titles, original_name):
            if job["url"] and job["url"] not in seen_urls:
                seen_urls.add(job["url"])
                all_jobs.append(job)
        time.sleep(0.5)

    return all_jobs
