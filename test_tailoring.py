"""
Standalone tailoring test — no pipeline, no DB, no LinkedIn.
Tailors resume and/or cover letter, then uploads to Google Drive as native Docs.

Usage:
  python test_tailoring.py                          # uses inputs/ defaults, your user (id=1)
  python test_tailoring.py --resume path/to/r.docx --cover path/to/cl.docx
  python test_tailoring.py --resume-only
  python test_tailoring.py --cover-only
  python test_tailoring.py --user-id 2              # use a different web user's Drive token

Outputs land in outputs/test_tailoring/ and are uploaded to Google Drive.
"""
import argparse
import os
import sys
from pathlib import Path

# Make src/ and web/ importable
_ROOT = Path(__file__).parent
sys.path.insert(0, str(_ROOT / "src"))
sys.path.insert(0, str(_ROOT))

from dotenv import load_dotenv
load_dotenv()

import anthropic
from tailor.resume_tailor import tailor_resume
from tailor.cover_letter_tailor import tailor_cover_letter

# ── Sample job (edit freely) ──────────────────────────────────────────────────
SAMPLE_JOB = {
    "company": "Acme Analytics",
    "title": "Senior Data Scientist",
    "description": (
        "We are looking for a Senior Data Scientist to join our growing team. "
        "You will build and deploy machine learning models, collaborate with "
        "cross-functional teams, and communicate insights to stakeholders. "
        "Required: Python, SQL, scikit-learn, experience with A/B testing, "
        "strong communication skills. Nice to have: Spark, dbt, LLM experience."
    ),
    "match_score": 82,
    "match_summary": "Strong ML and Python background; good fit for analytics role.",
    "recommended_keywords": [
        "cross-functional collaboration",
        "A/B testing",
        "stakeholder communication",
        "machine learning deployment",
        "scikit-learn",
    ],
}
# ─────────────────────────────────────────────────────────────────────────────


def upload(user_id: int, docx_path: str, title: str, cached_folder_id: str | None) -> tuple[str, str]:
    from web.drive_uploader import upload_to_user_drive
    return upload_to_user_drive(user_id, docx_path, title, cached_folder_id)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--resume", default="inputs/resume.docx")
    parser.add_argument("--cover", default="inputs/cover_letter.docx")
    parser.add_argument("--resume-only", action="store_true")
    parser.add_argument("--cover-only", action="store_true")
    parser.add_argument("--user-id", type=int, default=1,
                        help="Web user ID whose Google Drive token to use (default: 1)")
    args = parser.parse_args()

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        sys.exit("ANTHROPIC_API_KEY not set in .env")
    client = anthropic.Anthropic(api_key=api_key)

    out_dir = Path("outputs/test_tailoring")
    out_dir.mkdir(parents=True, exist_ok=True)

    do_resume = not args.cover_only
    do_cover = not args.resume_only
    folder_id = None

    if do_resume:
        src = Path(args.resume)
        if not src.exists():
            sys.exit(f"Resume not found: {src}")
        out = str(out_dir / "resume_tailored.docx")
        print(f"Tailoring resume: {src}")
        tailor_resume(SAMPLE_JOB, str(src), out, client)
        print(f"  Saved locally: {out}")
        try:
            url, folder_id = upload(args.user_id, out, "TEST — Acme Analytics Resume", folder_id)
            print(f"  Drive: {url}")
        except Exception as e:
            print(f"  Drive upload failed: {e}")

    if do_cover:
        src = Path(args.cover)
        if not src.exists():
            sys.exit(f"Cover letter not found: {src}")

        resume_text = ""
        if Path(args.resume).exists():
            from docx import Document
            doc = Document(args.resume)
            resume_text = "\n".join(p.text for p in doc.paragraphs if p.text.strip())

        out = str(out_dir / "cover_letter_tailored.docx")
        print(f"Tailoring cover letter: {src}")
        tailor_cover_letter(SAMPLE_JOB, str(src), out, client, resume_text=resume_text)
        print(f"  Saved locally: {out}")
        try:
            url, folder_id = upload(args.user_id, out, "TEST — Acme Analytics Cover Letter", folder_id)
            print(f"  Drive: {url}")
        except Exception as e:
            print(f"  Drive upload failed: {e}")

    print("\nDone.")


if __name__ == "__main__":
    main()
