# ZipRecruiter scraper
# Uses requests + BeautifulSoup to search for job listings

import json
import re
import time

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

BASE_URL = "https://www.ziprecruiter.com/candidate/search"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
}


def search_ziprecruiter(
    cities: list[str],
    titles: list[str],
    keywords: list[str],
    filters: dict,
) -> list[dict]:
    """
    Search ZipRecruiter for matching positions.
    Returns: [{"company", "title", "description", "url", "location", "posted_date", "source"}]
    """
    days = filters.get("posted_within_days", 30)
    all_jobs: list[dict] = []
    seen_urls: set[str] = set()

    retry = Retry(total=3, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504])
    session = requests.Session()
    session.mount("https://", HTTPAdapter(max_retries=retry))
    session.headers.update(HEADERS)

    for title in titles:
        for city in cities:
            if city.lower() == "remote":
                params = {
                    "search": title,
                    "location": "United States",
                    "days": days,
                    "remote": "1",
                }
            else:
                params = {
                    "search": title,
                    "location": city,
                    "days": days,
                }

            try:
                resp = session.get(BASE_URL, params=params, timeout=15)
                resp.raise_for_status()
                jobs = _parse_page(resp.text, city)

                for job in jobs:
                    url = job.get("url", "")
                    if url and url not in seen_urls:
                        seen_urls.add(url)
                        all_jobs.append(job)

                print(f"    ZipRecruiter: {len(jobs)} jobs — {title} / {city}")
            except requests.RequestException as e:
                print(f"    ZipRecruiter error ({title} / {city}): {e}")

            time.sleep(1.5)  # be polite

    return all_jobs


def _parse_page(html: str, city: str) -> list[dict]:
    """Extract job listings from a ZipRecruiter search results page."""
    soup = BeautifulSoup(html, "html.parser")
    jobs: list[dict] = []

    # Attempt 1: JSON-LD structured data (most reliable when present)
    for script in soup.find_all("script", {"type": "application/ld+json"}):
        try:
            data = json.loads(script.string or "")
            items = data if isinstance(data, list) else [data]
            for item in items:
                if item.get("@type") == "JobPosting":
                    job = _from_jsonld(item, city)
                    if job:
                        jobs.append(job)
        except (json.JSONDecodeError, AttributeError):
            continue

    if jobs:
        return jobs

    # Attempt 2: Parse HTML job cards
    cards = soup.find_all("article", class_=re.compile(r"job_result|jobCard", re.I))
    for card in cards:
        job = _from_card(card, city)
        if job:
            jobs.append(job)

    return jobs


def _from_jsonld(item: dict, city: str) -> dict | None:
    """Build a job dict from a JSON-LD JobPosting entry."""
    url = item.get("url") or item.get("sameAs", "")
    title = item.get("title", "")
    company = ""
    org = item.get("hiringOrganization")
    if isinstance(org, dict):
        company = org.get("name", "")

    description = item.get("description", "")
    if "<" in description:
        description = BeautifulSoup(description, "html.parser").get_text(" ", strip=True)

    if not url or not title:
        return None

    return {
        "company": company,
        "title": title,
        "description": description[:3000],
        "url": url,
        "location": city,
        "posted_date": item.get("datePosted", ""),
        "source": "ziprecruiter",
    }


def _from_card(card, city: str) -> dict | None:
    """Extract job info from an HTML job card element."""
    try:
        title_el = card.find(class_=re.compile(r"title", re.I)) or card.find("h2")
        company_el = card.find(class_=re.compile(r"company|employer", re.I))
        link_el = card.find("a", href=True)
        desc_el = card.find(class_=re.compile(r"description|snippet|summary", re.I))

        if not title_el or not link_el:
            return None

        href = link_el["href"]
        if not href.startswith("http"):
            href = "https://www.ziprecruiter.com" + href

        return {
            "company": company_el.get_text(strip=True) if company_el else "Unknown",
            "title": title_el.get_text(strip=True),
            "description": desc_el.get_text(" ", strip=True)[:3000] if desc_el else "",
            "url": href,
            "location": city,
            "posted_date": "",
            "source": "ziprecruiter",
        }
    except Exception:
        return None
