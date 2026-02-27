# Prompt: Cover Letter Tailoring

You are a professional cover letter writer. Tailor this cover letter for the specific job below.

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

1. **Replace ALL placeholders and the header company line**: Scan every paragraph for `[Company Name]` and `[Job Title]` and replace them with the actual values. Also update the short paragraph in the header that contains only the previous company name — change it to `{company}`. Do not leave any placeholder text in the output.

2. **Tailor the opening paragraph**: Update with the correct company and title. Optionally add a sentence drawing on the JD's specific requirements.

3. **Optimize the experience paragraph**: Keep the core content but adjust language to highlight the experience most relevant to this role. Match terminology from the JD. Pull in additional specific detail from the resume if it strengthens the fit.

4. **Rewrite the tailored alignment section**: Replace the placeholder paragraph(s) with a genuine, specific paragraph about why the candidate fits THIS role at THIS company — use specific details from the job description. If the placeholder spans multiple paragraph indices, write the full new content into the FIRST index and set ALL remaining placeholder indices to `""` (empty string) to clear them.

5. **Update the closing paragraph**: Replace `[Company Name]` with the actual company name.

6. Do NOT invent achievements or experience not in the resume. Preserve the candidate's voice and letter structure.

Return a JSON array for every paragraph that changes (including those cleared to `""`):
```json
[
  {"index": <paragraph_index>, "text": "<complete new paragraph text>"},
  ...
]
```

Only include paragraphs that change. Omit paragraphs that stay the same.
