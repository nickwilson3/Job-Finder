"""
Job Finder — Main Orchestrator

Usage:
    python src/main.py             # Full run
    python src/main.py --dry-run   # Print search params, no API calls
"""

import argparse
import os
import sys
import yaml
from dotenv import load_dotenv


def load_config() -> tuple[dict, dict]:
    """Load settings.yaml and criteria.yaml from config/."""
    with open("config/settings.yaml") as f:
        settings = yaml.safe_load(f)
    with open("config/criteria.yaml") as f:
        criteria = yaml.safe_load(f)
    return settings, criteria


def dry_run(settings: dict, criteria: dict) -> None:
    """Print search configuration without making any API or web calls."""
    print("\n=== Job Finder — Dry Run ===\n")
    print(f"Cities:        {settings['cities']}")
    print(f"Job Titles:    {settings['job_titles']}")
    print(f"Keywords:      {settings['keywords']}")
    print(f"Exclude:       {settings.get('exclude_keywords', [])}")
    print(f"Remote OK:     {settings['filters']['remote_options']}")
    print(f"Min Score:     {settings['filters']['min_match_score']}")
    print(f"Sources:       {[k for k, v in settings['sources'].items() if v]}")
    print(f"\nOutput:        {settings['output']['excel_file']}")
    print(f"Applications:  {settings['output']['applications_dir']}")
    print("\nDry run complete. Edit config/settings.yaml to adjust settings.\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Job Finder Agent")
    parser.add_argument("--dry-run", action="store_true", help="Print config only, no API calls")
    args = parser.parse_args()

    load_dotenv()
    settings, criteria = load_config()

    if args.dry_run:
        dry_run(settings, criteria)
        return

    # Validate environment
    if not os.getenv("ANTHROPIC_API_KEY"):
        print("ERROR: ANTHROPIC_API_KEY not set. Copy .env.example to .env and add your key.")
        sys.exit(1)

    # Verify inputs exist
    for f in ["inputs/resume.docx", "inputs/cover_letter.docx"]:
        if not os.path.exists(f):
            print(f"ERROR: Missing required input file: {f}")
            print("Add your resume and cover letter to the inputs/ directory.")
            sys.exit(1)

    # Full pipeline (implemented incrementally)
    print("Full pipeline not yet implemented. Run with --dry-run to verify config.")


if __name__ == "__main__":
    main()
