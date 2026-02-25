# Excel reporting module
# Creates and updates job_tracker.xlsx using openpyxl

COLUMNS = [
    "Company",
    "Job Title",
    "Brief Description",
    "Application URL",
    "Resume Path",
    "Cover Letter Path",
    "Match Score",
    "Date Found",
    "Status",
]


def init_workbook(output_path: str) -> None:
    """Create a new job_tracker.xlsx with headers if it doesn't exist."""
    # TODO: implement
    raise NotImplementedError


def append_job(output_path: str, job: dict) -> None:
    """
    Append a new row to job_tracker.xlsx for a processed job.

    Args:
        output_path: Path to job_tracker.xlsx
        job: Fully processed job dict including tailored file paths and match score
    """
    # TODO: implement
    raise NotImplementedError
