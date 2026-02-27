# Job match analysis using Claude API
# Scores job descriptions against the user's resume

import json
import re
from pathlib import Path

PROMPT_PATH = Path(__file__).parent.parent.parent / "prompts" / "job_analysis.md"


def score_job(job: dict, resume_text: str, criteria: dict, client, preference_context: str = "") -> dict:
    """
    Use Claude to score how well a job matches the user's resume.

    Args:
        job: Job dict with company, title, description, url, etc.
        resume_text: Plain text extracted from the user's resume
        criteria: Scoring weights and thresholds from criteria.yaml

    Returns:
        job dict with added fields:
        {
            ...,
            "match_score": int (0-100),
            "match_summary": str,
            "key_gaps": list[str],
            "key_strengths": list[str],
            "recommended_keywords": list[str],
        }
    """
    weights = criteria.get("scoring_weights", {})
    prompt_template = PROMPT_PATH.read_text()

    substitutions = {
        "resume_text": resume_text,
        "company": job.get("company", ""),
        "job_title": job.get("title", ""),
        "job_description": job.get("description", ""),
        "skills_weight": str(weights.get("skills_match", 40)),
        "experience_weight": str(weights.get("experience_level", 20)),
        "title_weight": str(weights.get("title_alignment", 20)),
        "industry_weight": str(weights.get("industry_fit", 10)),
        "location_weight": str(weights.get("location_fit", 10)),
        "preference_context": preference_context,
    }
    prompt = prompt_template
    for key, value in substitutions.items():
        prompt = prompt.replace(f"{{{key}}}", value)

    message = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )

    text = message.content[0].text

    # Extract JSON block from response
    json_match = re.search(r"\{.*\}", text, re.DOTALL)
    if not json_match:
        raise ValueError(f"No JSON found in Claude response:\n{text}")

    result = json.loads(json_match.group())

    return {
        **job,
        "match_score": result.get("match_score", 0),
        "match_summary": result.get("match_summary", ""),
        "key_strengths": result.get("key_strengths", []),
        "key_gaps": result.get("key_gaps", []),
        "recommended_keywords": result.get("recommended_keywords", []),
    }
