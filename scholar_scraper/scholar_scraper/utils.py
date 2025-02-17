# scholar_scraper/scholar_scraper/utils.py
import time
import random
from fake_useragent import UserAgent


def get_random_delay(min_delay=5, max_delay=15):
    """Returns a random delay between min_delay and max_delay seconds."""
    return random.uniform(min_delay, max_delay)


def get_random_user_agent():
    """Returns a random user agent string."""
    ua = UserAgent()
    return ua.random


def detect_captcha(html_content):
    """Detects if the page contains a CAPTCHA.  Basic implementation."""
    # Check for common CAPTCHA elements (very basic; needs refinement)
    if "sorry/image" in html_content or "gstatic.com/recaptcha" in html_content:
        return True
    return False
