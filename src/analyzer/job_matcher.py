# Job match analysis using Claude API
# Scores job descriptions against the user's resume


def score_job(job: dict, resume_text: str, criteria: dict, client) -> dict:
    """
    Use Claude to score how well a job matches the user's resume.

    Args:
        job: Job dict with company, title, description, url, etc.
        resume_text: Plain text extracted from the user's resume
        criteria: Scoring weights and thresholds from criteria.yaml
        client: Anthropic client instance

    Returns:
        job dict with added fields:
        {
            ...,
            "match_score": int (0-100),
            "match_summary": str,
            "key_gaps": list[str],
            "key_strengths": list[str]
        }
    """
    # TODO: implement
    raise NotImplementedError
