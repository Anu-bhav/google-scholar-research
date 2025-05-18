from enum import Enum

from google_scholar_scraper.models import ProxyErrorType


def test_proxy_error_type_enum():
    """Test the ProxyErrorType Enum members and properties."""
    # Check existence and type of members
    assert isinstance(ProxyErrorType.CONNECTION, ProxyErrorType)
    assert isinstance(ProxyErrorType.TIMEOUT, ProxyErrorType)
    assert isinstance(ProxyErrorType.FORBIDDEN, ProxyErrorType)
    assert isinstance(ProxyErrorType.OTHER, ProxyErrorType)
    assert isinstance(ProxyErrorType.CAPTCHA, ProxyErrorType)

    # Check names (optional, but good for confirming no typos)
    assert ProxyErrorType.CONNECTION.name == "CONNECTION"
    assert ProxyErrorType.TIMEOUT.name == "TIMEOUT"
    assert ProxyErrorType.FORBIDDEN.name == "FORBIDDEN"
    assert ProxyErrorType.OTHER.name == "OTHER"
    assert ProxyErrorType.CAPTCHA.name == "CAPTCHA"

    # Check number of members
    assert len(ProxyErrorType) == 5

    # Check that values are unique (auto() should ensure this)
    member_values = [member.value for member in ProxyErrorType]
    assert len(member_values) == len(set(member_values)), "Enum member values should be unique."

    # Check that they are instances of Enum as well
    for member in ProxyErrorType:
        assert isinstance(member, Enum)
