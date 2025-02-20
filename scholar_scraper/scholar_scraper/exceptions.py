class CaptchaException(Exception):
    """Raised when a CAPTCHA is detected on a webpage.

    Indicates that the scraper has encountered a CAPTCHA challenge,
    likely due to excessive requests or bot-like behavior.
    """

    pass


class ParsingException(Exception):
    """Raised when an error occurs during HTML parsing.

    Indicates that the scraper was unable to extract data from the HTML content
    as expected, possibly due to changes in the website's structure or
    unexpected content.
    """

    pass


class NoProxiesAvailable(Exception):
    """Raised when no working proxies are available.

    Indicates that the ProxyManager could not find any proxies that are
    currently working and not blacklisted.  This usually means proxy sources
    are exhausted or all proxies have failed.
    """

    pass
