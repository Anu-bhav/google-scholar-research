# utils.py
import random
import re
from typing import Optional  # Added Optional

from fake_useragent import UserAgent


def get_random_delay(min_delay=2, max_delay=5):
    """
    Generates a random delay between min_delay and max_delay seconds.

    This function is used to introduce delays between requests to avoid
    overloading servers and to mimic human-like browsing behavior, which can help
    prevent rate limiting or blocking.

    Args:
        min_delay (int, optional): Minimum delay in seconds. Defaults to 2.
        max_delay (int, optional): Maximum delay in seconds. Defaults to 5.

    Returns:
        float: A random delay value (in seconds) between min_delay and max_delay.

    """
    return random.uniform(min_delay, max_delay)


def get_random_user_agent():
    """
    Returns a random user agent string using the fake-useragent library.

    This function fetches a random user agent string, simulating different web browsers
    and operating systems.  Using a variety of user agents helps to avoid
    detection as a bot and reduces the chance of being blocked by websites.

    Returns:
        str: A random user agent string.

    """
    ua = UserAgent()
    return ua.random


def detect_captcha(html_content: Optional[str]) -> bool:
    """
    Detects CAPTCHA indicators in HTML content using regular expressions.

    This function searches for common patterns and phrases within the HTML content
    that are indicative of a CAPTCHA challenge page. CAPTCHA detection is crucial
    for web scraping to identify when anti-bot measures are triggered.

    Args:
        html_content (Optional[str]): The HTML content (as a string) to analyze for CAPTCHA indicators.

    Returns:
        bool: True if CAPTCHA is detected in the HTML content, False otherwise.

    """
    if not html_content:  # Handle None or empty string gracefully
        return False
    captcha_patterns = [
        r"prove\s+you'?re\s+human",
        r"verify\s+you'?re\s+not\s+a\s+robot",
        r"complete\s+the\s+CAPTCHA",
        r"security\s+check",
        r"/sorry/image",  # Google's reCAPTCHA image URL
        r"recaptcha",  # Common reCAPTCHA keyword
        r"hcaptcha",  # hCaptcha keyword
        r"<img\s+[^>]*src=['\"]data:image/png;base64,",  # inline captcha image
        r"<iframe\s+[^>]*src=['\"]https://www\.google\.com/recaptcha/api[2]?/",  # reCAPTCHA iframe
    ]
    for pattern in captcha_patterns:
        if re.search(pattern, html_content, re.IGNORECASE):
            return True
    return False
