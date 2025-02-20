# exceptions.py
class CaptchaException(Exception):
    """Raised when a CAPTCHA is detected on a webpage.

    Indicates that the scraper has encountered a CAPTCHA challenge,
    likely due to excessive requests or bot-like behavior.  Handling this
    exception typically involves rotating proxies, reducing request frequency,
    or implementing CAPTCHA solving mechanisms.
    """

    pass


class ParsingException(Exception):
    """Raised when an error occurs during HTML parsing.

    Indicates that the scraper was unable to extract data from the HTML content
    as expected. This could be due to changes in the website's structure,
    unexpected content format, or issues with the parsing logic itself.
    """

    pass


class NoProxiesAvailable(Exception):
    """Raised when no working proxies are available.

    Indicates that the ProxyManager could not find any proxies that are
    currently working and not blacklisted.  This usually means proxy sources
    are exhausted, all proxies have failed, or there are network connectivity issues
    preventing proxy retrieval or testing.
    """

    pass
