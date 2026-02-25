# Cover letter tailoring module
# Uses Claude API to identify keyword swaps, then python-docx to apply them


def tailor_cover_letter(job: dict, cover_letter_path: str, output_path: str, client) -> str:
    """
    Tailor the DOCX cover letter for a specific job by swapping keywords.
    Preserves all formatting — only changes specific words/phrases.

    Args:
        job: Job dict with description, title, company, match analysis
        cover_letter_path: Path to the base cover_letter.docx
        output_path: Where to save the tailored cover letter.docx
        client: Anthropic client instance

    Returns:
        Path to the saved tailored cover letter.docx
    """
    # TODO: implement
    raise NotImplementedError
