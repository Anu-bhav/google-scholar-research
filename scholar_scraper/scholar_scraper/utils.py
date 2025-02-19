# utils.py
import random
import re

from fake_useragent import UserAgent


def get_random_delay(min_delay=2, max_delay=5):
    return random.uniform(min_delay, max_delay)


def get_random_user_agent():
    ua = UserAgent()
    return ua.random


def detect_captcha(html_content: str) -> bool:
    """Detects CAPTCHA in HTML content."""
    # More robust CAPTCHA detection, including common phrases and patterns.
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
