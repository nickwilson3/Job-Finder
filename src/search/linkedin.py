# LinkedIn scraper
# Uses Playwright with a saved session file to bypass bot detection.
#
# FIRST-TIME SETUP:
#   Run: python src/search/linkedin.py --setup
#   A browser will open. Log in to LinkedIn manually, then press Enter in the terminal.
#   Your session is saved to inputs/linkedin_session.json for future runs.

import json
import time
from pathlib import Path
from urllib.parse import quote_plus

SESSION_FILE = Path("inputs/linkedin_session.json")
LINKEDIN_HOME = "https://www.linkedin.com"
JOB_SEARCH_URL = "https://www.linkedin.com/jobs/search/"


def search_linkedin(
    cities: list[str],
    titles: list[str],
    keywords: list[str],
    filters: dict,
) -> list[dict]:
    """
    Search LinkedIn Jobs for matching positions using a saved Playwright session.
    Returns: [{"company", "title", "description", "url", "location", "posted_date", "source"}]

    Requires inputs/linkedin_session.json — run with --setup to create it.
    """
    from playwright.sync_api import sync_playwright

    if not SESSION_FILE.exists():
        print(
            f"\n  LinkedIn: no session file found at {SESSION_FILE}\n"
            "  Run: python src/search/linkedin.py --setup\n"
            "  Then re-run the agent.\n"
        )
        return []

    cookies = json.loads(SESSION_FILE.read_text())
    days = filters.get("posted_within_days", 30)
    seconds = days * 24 * 3600  # LinkedIn time filter uses seconds

    all_jobs: list[dict] = []
    seen_urls: set[str] = set()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            )
        )
        context.add_cookies(cookies)
        page = context.new_page()

        for title in titles:
            for city in cities:
                location = "Remote" if city.lower() == "remote" else city
                params = (
                    f"?keywords={quote_plus(title)}"
                    f"&location={quote_plus(location)}"
                    f"&f_TPR=r{seconds}"
                    "&position=1&pageNum=0"
                )
                url = JOB_SEARCH_URL + params

                try:
                    page.goto(url, wait_until="domcontentloaded", timeout=20000)
                    time.sleep(2)  # let dynamic content settle

                    jobs = _parse_job_list(page, city)
                    for job in jobs:
                        job_url = job.get("url", "")
                        if job_url and job_url not in seen_urls:
                            seen_urls.add(job_url)
                            all_jobs.append(job)

                    print(f"    LinkedIn: {len(jobs)} jobs — {title} / {city}")
                except Exception as e:
                    print(f"    LinkedIn error ({title} / {city}): {e}")

                time.sleep(2)

        browser.close()

    return all_jobs


def _parse_job_list(page, city: str) -> list[dict]:
    """Extract job cards from the LinkedIn job search results page."""
    jobs: list[dict] = []

    cards = page.query_selector_all(
        "li.jobs-search-results__list-item, div.job-search-card"
    )

    for card in cards:
        try:
            title_el = card.query_selector(
                "a.job-card-list__title, h3.base-search-card__title, .job-card-container__link"
            )
            company_el = card.query_selector(
                "a.job-card-container__company-name, h4.base-search-card__subtitle"
            )
            link_el = card.query_selector("a[href*='/jobs/view/']")
            location_el = card.query_selector(
                "span.job-card-container__metadata-item, span.job-search-card__location"
            )
            time_el = card.query_selector("time[datetime]")

            if not title_el or not link_el:
                continue

            href = link_el.get_attribute("href") or ""
            if "?" in href:
                href = href.split("?")[0]

            posted_date = ""
            if time_el:
                posted_date = time_el.get_attribute("datetime") or ""

            jobs.append({
                "company": company_el.inner_text().strip() if company_el else "Unknown",
                "title": title_el.inner_text().strip(),
                "description": "",  # populated by fetch_job_description if score passes
                "url": href,
                "location": location_el.inner_text().strip() if location_el else city,
                "posted_date": posted_date,
                "source": "linkedin",
            })
        except Exception:
            continue

    return jobs


def fetch_descriptions_batch(jobs: list[dict]) -> None:
    """
    Fetch LinkedIn job descriptions for a batch of jobs using a single browser context.
    Mutates each job dict's 'description' field in place.
    Only processes jobs from LinkedIn source with empty descriptions.
    """
    from playwright.sync_api import sync_playwright

    if not SESSION_FILE.exists():
        print("  LinkedIn: no session file, skipping description fetch.")
        return

    linkedin_jobs = [j for j in jobs if j.get("source") == "linkedin" and not j.get("description")]
    if not linkedin_jobs:
        return

    cookies = json.loads(SESSION_FILE.read_text())

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            )
        )
        context.add_cookies(cookies)
        page = context.new_page()

        for job in linkedin_jobs:
            url = job.get("url", "")
            if not url:
                continue
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=20000)
                time.sleep(1.5)
                desc_el = page.query_selector(
                    "div.jobs-description__content, div.description__text"
                )
                if desc_el:
                    job["description"] = desc_el.inner_text().strip()[:3000]
            except Exception as e:
                print(f"    Description fetch failed ({job.get('company')} — {job.get('title')}): {e}")
            time.sleep(1.5)

        browser.close()


def setup_session() -> None:
    """
    Interactive first-time setup: open a visible browser, let the user log in,
    then save session cookies to inputs/linkedin_session.json.
    """
    from playwright.sync_api import sync_playwright

    SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)

    print("\nOpening browser for LinkedIn login...")
    print("Log in to LinkedIn, then come back here and press Enter.\n")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()
        page.goto(LINKEDIN_HOME)

        input("Press Enter once you are logged in to LinkedIn...")

        cookies = context.cookies()
        SESSION_FILE.write_text(json.dumps(cookies, indent=2))
        print(f"\nSession saved to {SESSION_FILE}")
        browser.close()


if __name__ == "__main__":
    import sys
    if "--setup" in sys.argv:
        setup_session()
    else:
        print("Usage: python src/search/linkedin.py --setup")
