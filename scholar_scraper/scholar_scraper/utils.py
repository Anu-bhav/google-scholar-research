# utils.py
import random
import re

from fake_useragent import UserAgent


def get_random_delay(min_delay=2, max_delay=5):
    """Generates a random delay between min_delay and max_delay seconds.

    Args:
        min_delay (int, optional): Minimum delay in seconds. Defaults to 2.
        max_delay (int, optional): Maximum delay in seconds. Defaults to 5.

    Returns:
        float: A random delay value between min_delay and max_delay.

    """
    return random.uniform(min_delay, max_delay)


def get_random_user_agent():
    """Returns a random user agent string using the fake-useragent library.

    Returns:
        str: A random user agent string.

    """
    ua = UserAgent()
    return ua.random


def detect_captcha(html_content: str) -> bool:
    """Detects CAPTCHA indicators in HTML content using regular expressions.

    Args:
        html_content (str): The HTML content to analyze.

    Returns:
        bool: True if CAPTCHA is detected, False otherwise.

    """
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
