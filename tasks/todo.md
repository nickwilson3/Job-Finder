# Job Finder — Task Tracker

## Phase 1: Scaffold (Complete)
- [x] Clone repo
- [x] Create CLAUDE.md
- [x] Create folder structure
- [x] Create requirements.txt
- [x] Create config/settings.yaml and criteria.yaml templates
- [x] Create .gitignore
- [x] Create src/main.py skeleton with --dry-run support
- [x] Create module stubs (search, analyzer, tailor, reporter)
- [x] Create prompt templates
- [x] Initial commit and push

## Phase 2: Core Pipeline (Next Session)
- [ ] Implement `src/reporter/excel_reporter.py` — init and append to xlsx
- [ ] Implement `src/analyzer/job_matcher.py` — Claude API job scoring
- [ ] Implement `src/tailor/resume_tailor.py` — DOCX keyword swaps
- [ ] Implement `src/tailor/cover_letter_tailor.py` — DOCX keyword swaps
- [ ] Wire up full pipeline in `src/main.py`
- [ ] Test end-to-end with a single sample job

## Phase 3: Job Search (After Pipeline Works)
- [ ] Implement `src/search/ziprecruiter.py`
- [ ] Implement `src/search/linkedin.py` (Playwright + session cookies)
- [ ] Implement `src/search/company_sites.py` (Google site: search)
- [ ] Integration test: full search → score → tailor → Excel row

## Phase 4: Polish
- [ ] Add deduplication (skip jobs already in tracker)
- [ ] Add PDF export (docx2pdf)
- [ ] Add logging and run summary
- [ ] Add rate limiting / retry logic for scrapers
