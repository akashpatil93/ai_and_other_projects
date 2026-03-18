import requests
from bs4 import BeautifulSoup
from typing import Tuple


LINKEDIN_FALLBACK_MESSAGE = (
    "LinkedIn blocks automated access to profile pages. "
    "To include your LinkedIn data, please go to your LinkedIn profile → "
    "More → Save to PDF, then upload that PDF in the resume section above. "
    "Your LinkedIn content will still be used to tailor your resume."
)


def fetch_linkedin_profile(url: str) -> Tuple[bool, str]:
    """
    Attempt to scrape a LinkedIn profile URL.
    Returns (success: bool, content_or_message: str).
    LinkedIn aggressively blocks scrapers, so failure is expected and handled gracefully.
    """
    if "linkedin.com/in/" not in url:
        return False, (
            "That doesn't look like a LinkedIn profile URL. "
            "Expected format: https://linkedin.com/in/your-name. "
            + LINKEDIN_FALLBACK_MESSAGE
        )

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://www.google.com/",
    }

    try:
        response = requests.get(url, headers=headers, timeout=15)

        # LinkedIn returns 999 or 302→login for blocked requests
        if response.status_code in (999, 403, 401) or "authwall" in response.url:
            return False, LINKEDIN_FALLBACK_MESSAGE

        response.raise_for_status()
        soup = BeautifulSoup(response.content, "html.parser")

        for tag in soup(["script", "style", "nav", "footer"]):
            tag.decompose()

        text = soup.get_text(separator="\n", strip=True)
        lines = [
            line.strip()
            for line in text.splitlines()
            if line.strip() and len(line.strip()) > 3
        ]
        content = "\n".join(lines[:300])

        # If we got very little content it's likely a login wall
        if len(content) < 200:
            return False, LINKEDIN_FALLBACK_MESSAGE

        return True, content

    except requests.exceptions.RequestException:
        return False, LINKEDIN_FALLBACK_MESSAGE
