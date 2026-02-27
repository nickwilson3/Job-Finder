# Preference learner — builds a preference profile from past application decisions.
# Called once per run before scoring. Returns a short summary string injected into
# the scoring prompt so Claude understands the user's revealed preferences.


def build_preference_context(
    applied: list[dict],
    skipped: list[dict],
    client,
) -> str:
    """
    Use Haiku to summarize the user's application preferences from history.

    Args:
        applied: Jobs the user marked "Applied" — each has company, title, summary
        skipped: Jobs the user marked "Did Not Apply"
        client: Anthropic client instance

    Returns:
        2-3 sentence preference profile, or '' if fewer than 5 total decisions.
    """
    if len(applied) + len(skipped) < 5:
        return ""

    applied_text = "\n".join(
        f"- {j['title']} at {j['company']}: {j.get('summary', '')}"
        for j in applied[:30]
    )
    skipped_text = "\n".join(
        f"- {j['title']} at {j['company']}: {j.get('summary', '')}"
        for j in skipped[:30]
    )

    prompt = f"""Analyze this job seeker's application history to identify their preferences.

JOBS THEY APPLIED TO:
{applied_text or '(none yet)'}

JOBS THEY DID NOT APPLY TO:
{skipped_text or '(none yet)'}

In 2-3 concise sentences, describe: what types of roles, companies, and industries \
they prefer, and what they consistently avoid. Be specific and actionable.
Return ONLY the summary sentences, no preamble or explanation."""

    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=256,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text.strip()
