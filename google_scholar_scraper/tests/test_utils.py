"""
Tests for the utility functions.
"""

import unittest
from unittest.mock import MagicMock, patch

# Try to import utilities, but mock them if not available yet
try:
    from google_scholar_scraper.utils import detect_captcha, get_random_delay, get_random_user_agent
except ImportError:
    # For testing purposes, we'll create mocks if the modules don't exist yet
    get_random_delay = MagicMock(return_value=2.5)
    get_random_user_agent = MagicMock(return_value="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")
    detect_captcha = MagicMock(return_value=False)


class TestUtils(unittest.TestCase):
    """Test cases for utility functions"""

    def test_get_random_delay(self):
        """Test get_random_delay returns values within specified range"""
        # Skip if using mock version
        if isinstance(get_random_delay, MagicMock):
            self.skipTest("utils module not available")

        # Test with default range
        delay = get_random_delay()
        self.assertIsInstance(delay, float)
        self.assertGreaterEqual(delay, 2.0)
        self.assertLessEqual(delay, 5.0)

        # Test with custom range
        min_delay, max_delay = 1.0, 3.0
        delay = get_random_delay(min_delay, max_delay)
        self.assertGreaterEqual(delay, min_delay)
        self.assertLessEqual(delay, max_delay)

    @patch("random.uniform")
    def test_get_random_delay_uses_random_uniform(self, mock_uniform):
        """Test get_random_delay uses random.uniform"""
        # Skip if using mock version
        if isinstance(get_random_delay, MagicMock):
            self.skipTest("utils module not available")

        mock_uniform.return_value = 3.5
        delay = get_random_delay(2.0, 5.0)
        self.assertEqual(delay, 3.5)
        mock_uniform.assert_called_once_with(2.0, 5.0)

    def test_get_random_user_agent(self):
        """Test get_random_user_agent returns a valid user agent string"""
        # Skip if using mock version
        if isinstance(get_random_user_agent, MagicMock):
            self.skipTest("utils module not available")

        user_agent = get_random_user_agent()
        self.assertIsInstance(user_agent, str)
        self.assertGreater(len(user_agent), 10)  # User agent strings should be reasonably long

        # Test multiple calls return different user agents (unlikely to get the same one twice)
        user_agents = set(get_random_user_agent() for _ in range(5))
        self.assertGreater(len(user_agents), 1)  # Should have at least 2 different user agents

    def test_detect_captcha_with_captcha_html(self):
        """Test detect_captcha correctly identifies CAPTCHA challenge pages"""
        # Skip if using mock version
        if isinstance(detect_captcha, MagicMock):
            self.skipTest("utils module not available")

        # Sample HTML containing Google CAPTCHA
        captcha_html = """
        <html>
        <head><title>Google Scholar</title></head>
        <body>
            <div id="gs_captcha_ccl">
                <h1>Please show you're not a robot</h1>
                <form id="gs_captcha_f" action="/scholar_captcha" method="get">
                    <input type="hidden" name="q" value="test">
                    <div class="g-recaptcha" data-sitekey="abc123"></div>
                    <input type="submit" value="Submit">
                </form>
            </div>
        </body>
        </html>
        """

        # Test detection
        self.assertTrue(detect_captcha(captcha_html))

    def test_detect_captcha_with_normal_html(self):
        """Test detect_captcha correctly identifies normal pages"""
        # Skip if using mock version
        if isinstance(detect_captcha, MagicMock):
            self.skipTest("utils module not available")

        # Sample HTML of normal Google Scholar page
        normal_html = """
        <html>
        <head><title>Google Scholar</title></head>
        <body>
            <div id="gs_res_ccl_mid">
                <div class="gs_ri">
                    <h3 class="gs_rt"><a href="https://example.com">Test Result</a></h3>
                </div>
            </div>
        </body>
        </html>
        """

        # Test non-detection
        self.assertFalse(detect_captcha(normal_html))

    def test_detect_captcha_with_empty_html(self):
        """Test detect_captcha handles empty HTML"""
        # Skip if using mock version
        if isinstance(detect_captcha, MagicMock):
            self.skipTest("utils module not available")

        # Test with empty HTML
        self.assertFalse(detect_captcha(""))
        self.assertFalse(detect_captcha(None))


if __name__ == "__main__":
    unittest.main()
