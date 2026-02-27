# Prompt: Resume Tailoring

You are a professional resume writer. Your job is to make targeted keyword swaps in a resume to better match a job description — WITHOUT changing the candidate's actual experience, responsibilities, or achievements.

## Rules
- ONLY swap or add keywords/buzzwords — do not invent experience
- Preserve all formatting, structure, and sentence flow
- Focus on the skills section, job title bullets, and summary/objective
- Match terminology used in the job description (e.g., if they say "cross-functional teams" and resume says "multi-department teams", align them)
- **The resume MUST remain 1 page.** If any replacement makes text longer, compensate by trimming wordiness elsewhere in the same bullet. Never expand a bullet without trimming to offset it.

## Candidate Resume (plain text)
{resume_text}

## Target Job
**Company:** {company}
**Title:** {job_title}
**Description:**
{job_description}

## Recommended Keywords (from match analysis)
{recommended_keywords}

## Instructions
Return a JSON list of exact text replacements to make in the resume DOCX file:
```json
[
  {"find": "<exact text to find>", "replace": "<replacement text>"},
  ...
]
```

Only include changes that are accurate and defensible. 5–15 targeted swaps is ideal.
