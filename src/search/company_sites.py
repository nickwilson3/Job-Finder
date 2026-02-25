# Company career page search module
# Uses Google search with site: operator to find job postings on company career pages


def search_company_sites(cities: list[str], titles: list[str], keywords: list[str], filters: dict) -> list[dict]:
    """
    Search company career pages via Google for matching positions.

    Returns a list of job dicts:
    {
        "company": str,
        "title": str,
        "description": str,
        "url": str,
        "location": str,
        "posted_date": str,
        "source": "company_site"
    }
    """
    # TODO: implement
    raise NotImplementedError
