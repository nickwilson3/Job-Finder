# Cover letter tailoring module
# Haiku receives the template with numbered paragraphs + resume + JD,
# then returns JSON specifying which paragraph indices to update.
# Paragraph-index replacement preserves all DOCX formatting (fonts, spacing, layout).

import json
import re
import shutil
from pathlib import Path

from docx import Document

PROMPT_PATH = Path(__file__).parent.parent.parent / "prompts" / "cover_letter_tailor.md"


def _numbered_paragraphs(doc: Document) -> str:
    """Return non-empty template paragraphs as '[index] text' lines for the prompt."""
    lines = []
    for i, para in enumerate(doc.paragraphs):
        if para.text.strip():
            lines.append(f"[{i}] {para.text}")
    return "\n".join(lines)


def _apply_paragraph_replacements(doc: Document, replacements: list[dict]) -> None:
    """Replace paragraph content by index, preserving DOCX run formatting."""
    for item in replacements:
        idx = item.get("index")
        new_text = item.get("text", "")
        if idx is None or not isinstance(idx, int):
            continue
        if idx >= len(doc.paragraphs):
            continue
        para = doc.paragraphs[idx]
        if para.runs:
            para.runs[0].text = new_text
            for run in para.runs[1:]:
                run.text = ""
        elif new_text:
            para.add_run(new_text)


def tailor_cover_letter(job: dict, cover_letter_path: str, output_path: str, client, resume_text: str = "") -> str:
    """
    Tailor the DOCX cover letter for a specific job.

    Haiku sees the numbered template paragraphs, resume, and job description,
    then returns which paragraph indices to update and what to write in each.
    Only the text content changes — all DOCX formatting is preserved.
    """
    template_doc = Document(cover_letter_path)
    template_numbered = _numbered_paragraphs(template_doc)

    prompt_template = PROMPT_PATH.read_text()
    substitutions = {
        "template_numbered": template_numbered,
        "resume_text": resume_text,
        "company": job.get("company", ""),
        "job_title": job.get("title", ""),
        "job_description": job.get("description", ""),
    }
    prompt = prompt_template
    for key, value in substitutions.items():
        prompt = prompt.replace(f"{{{key}}}", value)

    message = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
    )

    text = message.content[0].text

    # Extract JSON array from response
    json_match = re.search(r"\[.*\]", text, re.DOTALL)
    if not json_match:
        raise ValueError(f"No JSON array found in Claude response:\n{text}")

    replacements = json.loads(json_match.group())

    # Copy base cover letter and apply paragraph replacements
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(cover_letter_path, output_path)

    doc = Document(output_path)
    _apply_paragraph_replacements(doc, replacements)
    doc.save(output_path)

    return output_path
