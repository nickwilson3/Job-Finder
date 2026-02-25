# LinkedIn job search module
# Uses Playwright with saved session cookies to avoid bot detection


def search_linkedin(cities: list[str], titles: list[str], keywords: list[str], filters: dict) -> list[dict]:
    """
    Search LinkedIn Jobs for matching positions.

    Returns a list of job dicts:
    {
        "company": str,
        "title": str,
        "description": str,
        "url": str,
        "location": str,
        "posted_date": str,
        "source": "linkedin"
    }
    """
    # TODO: implement
    raise NotImplementedError
