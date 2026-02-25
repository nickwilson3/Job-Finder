# Resume tailoring module
# Uses Claude API to identify keyword swaps, then python-docx to apply them


def tailor_resume(job: dict, resume_path: str, output_path: str, client) -> str:
    """
    Tailor the DOCX resume for a specific job by swapping keywords.
    Preserves all formatting — only changes specific words/phrases.

    Args:
        job: Job dict with description, title, company, match analysis
        resume_path: Path to the base resume.docx
        output_path: Where to save the tailored resume.docx
        client: Anthropic client instance

    Returns:
        Path to the saved tailored resume.docx
    """
    # TODO: implement
    raise NotImplementedError
