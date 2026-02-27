# Job Finder Agent

An automated job search and application pipeline powered by Claude AI. Searches LinkedIn and company career pages, scores each posting against your profile, tailors your resume and cover letter for every strong match, and tracks everything in Google Sheets with direct links to Google Docs.

---

## What It Does

1. **Searches** LinkedIn and company ATS boards (Greenhouse, Lever) for matching postings
2. **Deduplicates** against your full application history across all past runs
3. **Prioritizes** by posting date — newest jobs are processed first
4. **Scores** each job 0–100 using Claude Haiku, weighted across skills, experience, title, industry, and location
5. **Learns** your preferences over time — after you mark jobs as Applied/Did Not Apply, future scoring reflects what you actually apply to
6. **Tailors** your resume and cover letter for every job above your score threshold (Haiku)
7. **Uploads** tailored docs to Google Drive as native Google Docs (quota-free, preserves formatting)
8. **Tracks** everything in Google Sheets — one date-stamped tab per run, color-coded by score, with clickable Drive links

---

## Prerequisites

- Python 3.11+
- An [Anthropic API key](https://console.anthropic.com)
- A Google account with Google Sheets, Drive, and Docs APIs enabled
- A LinkedIn account

---

## Setup

### 1. Install dependencies

```bash
pip install -r requirements.txt
playwright install chromium
```

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env and add your ANTHROPIC_API_KEY
```

### 3. Add your documents

Place these files in `inputs/`:
- `inputs/resume.docx` — your base resume
- `inputs/cover_letter.docx` — your cover letter template (use `[Job Title]` and `[Company Name]` as placeholders where appropriate)

### 4. Configure your profile

Edit **`config/settings.yaml`** — cities, job titles, keywords, sources, and output settings.

Edit **`config/criteria.yaml`** — your skills, experience level, scoring weights, and deal-breakers.

### 5. Set up Google Sheets

1. Create a Google Cloud project and enable the **Sheets API**, **Drive API**, and **Docs API**
2. Create a **Service Account**, download its JSON key → save as `inputs/google_credentials.json`
3. Create an **OAuth 2.0 Desktop App** credential → download JSON → save as `inputs/oauth_credentials.json`
4. Create a Google Sheet and share it with the service account email (Editor)
5. Copy the Sheet ID from its URL and paste into `config/settings.yaml` → `google_sheet_id`
6. Create a Drive folder for output docs, share it with the service account (Editor), copy the folder ID → `config/settings.yaml` → `drive_output_folder_id`

The first run will open a browser for one-time OAuth consent. The token is cached in `inputs/oauth_token.json` — no browser needed after that.

### 6. Set up LinkedIn session

```bash
python src/search/linkedin.py --setup
```

A browser opens. Log in to LinkedIn manually, then press Enter. Your session is saved to `inputs/linkedin_session.json`.

---

## Running

```bash
# Dry run — prints config, no API calls
python src/main.py --dry-run

# Full run
python src/main.py
```

---

## How the Pipeline Works

```
LinkedIn scrape (~1000 jobs)
    ↓
Company sites — Greenhouse + Lever (top companies from LinkedIn)
    ↓
Deduplicate within run + against all historical Sheet tabs
    ↓
Sort by posting date (newest first) → cap to max_jobs_per_run
    ↓
Load application history → build preference profile (Haiku, if ≥5 decisions)
    ↓
Fetch full job descriptions (LinkedIn jobs, single browser session)
    ↓
Score each job (Haiku) — weighted match score 0–100
    ↓
For jobs above min_score_to_tailor:
    ├── Tailor resume (Haiku) — targeted keyword swaps
    ├── Tailor cover letter (Haiku) — genuine paragraph rewrite
    └── Upload both to Google Drive as native Google Docs
    ↓
Append to Google Sheet (today's tab) — score, links, color-coded row
```

---

## Google Sheet Structure

Each run creates a new tab named by date (e.g., `2026-02-27`). Columns:

| Company | Job Title | Brief Description | Application URL | Resume | Cover Letter | Match Score | Date Found | Applied | Status |
|---------|-----------|-------------------|-----------------|--------|--------------|-------------|------------|---------|--------|

**Color coding:**
- Green: score ≥ 85 (strong match)
- Yellow: score ≥ 70

After reviewing each batch, fill in the **Applied** column:
- Applied: `Applied`, `Yes`, or `Y`
- Skipped: `Did Not Apply`, `No`, `N`, or `Skip`

This feedback trains the preference learner — after 5+ decisions, future scoring adjusts to match your revealed preferences.

---

## Project Structure

```
job-finder/
├── config/
│   ├── settings.yaml        # Cities, titles, sources, output settings
│   └── criteria.yaml        # Your profile, scoring weights, deal-breakers
├── inputs/                  # gitignored — add your files here
│   ├── resume.docx
│   ├── cover_letter.docx
│   ├── google_credentials.json
│   ├── oauth_credentials.json
│   └── linkedin_session.json
├── outputs/
│   └── applications/        # Local DOCX backups (gitignored)
├── prompts/
│   ├── job_analysis.md      # Scoring prompt
│   ├── resume_tailor.md     # Resume tailoring prompt
│   └── cover_letter_tailor.md
├── src/
│   ├── main.py              # Pipeline orchestrator
│   ├── search/
│   │   ├── linkedin.py      # Playwright scraper
│   │   └── company_sites.py # Greenhouse + Lever APIs
│   ├── analyzer/
│   │   ├── job_matcher.py   # Claude scoring
│   │   └── preference_learner.py  # RL from application history
│   ├── tailor/
│   │   ├── resume_tailor.py
│   │   └── cover_letter_tailor.py
│   └── reporter/
│       └── excel_reporter.py  # Google Sheets + Drive
└── requirements.txt
```

---

## Cost Profile

All AI calls use **Claude Haiku** — roughly:
- ~$0.001 per job scored
- ~$0.003 per resume tailored
- ~$0.003 per cover letter tailored
- ~$0.001 per run for preference learning

A typical run of 50 jobs (20 tailored) costs around **$0.15–0.20**.
