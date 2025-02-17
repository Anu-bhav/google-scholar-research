# scholar_scraper/scholar_scraper/exceptions.py
class CaptchaException(Exception):
    """Raised when a CAPTCHA is detected."""

    pass


class ParsingException(Exception):
    """Raised when an error occurs during parsing."""

    pass


class NoProxiesAvailable(Exception):
    """Raised when no working proxies are found"""

    pass
