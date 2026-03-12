# Prompt: Cover Letter Tailoring

You are a professional cover letter editor. Tailor this cover letter for the specific job below.

## Cover Letter Template
Each non-blank paragraph is shown with its index in [brackets]. You will reference these indices in your output.

{template_numbered}

## Candidate Resume (for context — do NOT invent experience)
{resume_text}

## Target Job
**Company:** {company}
**Title:** {job_title}
**Description:**
{job_description}

## Instructions

1. **Clean the header address block**: Between the candidate's contact info at the top and the "Dear Hiring Manager," greeting, there may be lines for a recipient name, street address, and city/state/zip. Clear ALL such lines by setting them to `""`. Set the remaining Company Name line (the one that contains only the previous company name) to `{company}`. Do NOT touch the candidate's own name or contact information at the top.

2. **Tailor the opening paragraph**: Update with the correct company and title. Optionally add a sentence drawing on the JD's specific requirements.

3. **Adjust language in the experience paragraph**: Keep the core content and structure. Adjust terminology to highlight experience most relevant to this role and match language from the JD. Pull in specific detail from the resume if it strengthens the fit. Do not rewrite the paragraph wholesale — preserve the candidate's voice.

4. **Update the tailored alignment section**: Adjust the paragraph(s) that speak to why the candidate fits this specific role. Use details from the job description to make it specific and genuine. Preserve the candidate's voice and sentence structure. If the section spans multiple paragraph indices, write the full updated content into the FIRST index and set remaining placeholder indices to `""`.

5. **Update the closing paragraph**: Replace any `[Company Name]` placeholder with the actual company name.

6. Do NOT invent achievements or experience not in the resume.

7. **Preserve the closing exactly**: Do not modify the "Sincerely," line or the candidate's name/signature below it. Leave those paragraph indices unchanged.

Return a JSON array for every paragraph that changes (including those cleared to `""`):
```json
[
  {"index": <paragraph_index>, "text": "<complete new paragraph text>"},
  ...
]
```

Only include paragraphs that change. Omit paragraphs that stay the same.
