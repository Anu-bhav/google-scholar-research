# models.py
from enum import Enum, auto


class ProxyErrorType(Enum):
    CONNECTION = auto()
    TIMEOUT = auto()
    FORBIDDEN = auto()
    OTHER = auto()
    CAPTCHA = auto()  # Specifically handle CAPTCHA
