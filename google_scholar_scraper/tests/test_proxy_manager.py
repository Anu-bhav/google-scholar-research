"""
Tests for the ProxyManager module.
"""

import asyncio
import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from fp.fp import FreeProxy
from google_scholar_scraper.models import ProxyErrorType  # Import ProxyErrorType
from google_scholar_scraper.proxy_manager import ProxyManager


class TestProxyManager(unittest.TestCase):
    """Test cases for ProxyManager class"""

    def setUp(self):
        """Set up test environment"""
        # Create a temporary blacklist file for testing
        self.temp_blacklist = tempfile.NamedTemporaryFile(delete=False, suffix=".json")
        self.temp_blacklist.close()

        # Default configuration
        self.timeout = 10
        self.refresh_interval = 60
        self.blacklist_duration = 3600
        self.num_proxies = 5

        # Create ProxyManager instance with test configuration
        self.proxy_manager = ProxyManager(
            timeout=self.timeout,
            refresh_interval=self.refresh_interval,
            blacklist_duration=self.blacklist_duration,
            num_proxies=self.num_proxies,
            blacklist_file=self.temp_blacklist.name,
        )

    def tearDown(self):
        """Clean up after tests"""
        # Remove temporary blacklist file
        if os.path.exists(self.temp_blacklist.name):
            os.unlink(self.temp_blacklist.name)

    def test_init_default_parameters(self):
        """Test __init__ method with default parameters"""
        proxy_manager = ProxyManager()

        # Verify default values
        self.assertEqual(proxy_manager.timeout, 5)  # Default timeout is 5
        self.assertEqual(proxy_manager.refresh_interval, 300)  # Default refresh_interval is 300
        self.assertEqual(proxy_manager.blacklist_duration, 600)  # Default blacklist_duration is 600
        self.assertEqual(proxy_manager.num_proxies, 20)  # Default num_proxies is 20
        self.assertEqual(proxy_manager.blacklist_file, "proxy_blacklist.json")

    def test_init_custom_parameters(self):
        """Test __init__ method with custom parameters"""
        # Values are set in setUp method
        self.assertEqual(self.proxy_manager.timeout, self.timeout)
        self.assertEqual(self.proxy_manager.refresh_interval, self.refresh_interval)
        self.assertEqual(self.proxy_manager.blacklist_duration, self.blacklist_duration)
        self.assertEqual(self.proxy_manager.num_proxies, self.num_proxies)
        self.assertEqual(self.proxy_manager.blacklist_file, self.temp_blacklist.name)

    def test_load_blacklist_non_existent_file(self):
        """Test _load_blacklist with non-existent blacklist file"""
        # Create instance with non-existent file
        non_existent_file = "non_existent_blacklist.json"
        proxy_manager = ProxyManager(blacklist_file=non_existent_file)

        # Verify blacklist is empty
        self.assertEqual(proxy_manager.blacklist, {})

    def test_load_blacklist_existing_file(self):
        """Test _load_blacklist with existing valid blacklist file"""
        # Create sample blacklist data
        # Blacklist stores timestamp directly as string
        blacklist_data = {"192.168.1.1:8080": str(datetime.now().timestamp())}

        # Write data to temporary file
        with open(self.temp_blacklist.name, "w") as f:
            json.dump(blacklist_data, f)

        # Initialize new proxy manager that will load the blacklist
        proxy_manager = ProxyManager(blacklist_file=self.temp_blacklist.name)

        # Verify blacklist is loaded correctly
        self.assertEqual(len(proxy_manager.blacklist), 1)
        self.assertIn("192.168.1.1:8080", proxy_manager.blacklist)
        # Reason is not stored directly with the timestamp in the new format
        # self.assertEqual(proxy_manager.blacklist["192.168.1.1:8080"]["reason"], "Connection error")
        self.assertIn("192.168.1.1:8080", proxy_manager.blacklist)  # Verify key exists

    def test_load_blacklist_expired_entries(self):
        """Test _load_blacklist removes expired blacklist entries"""
        # Create blacklist with expired and non-expired entries
        now = datetime.now().timestamp()
        expired_time = (datetime.now() - timedelta(seconds=self.blacklist_duration * 2)).timestamp()

        blacklist_data = {
            "expired.proxy:8080": str(expired_time),
            "valid.proxy:8080": str(now),
        }

        # Write data to temporary file
        with open(self.temp_blacklist.name, "w") as f:
            json.dump(blacklist_data, f)

        # Initialize new proxy manager that will load the blacklist
        proxy_manager = ProxyManager(blacklist_duration=self.blacklist_duration, blacklist_file=self.temp_blacklist.name)

        # Verify only non-expired entry remains
        self.assertEqual(len(proxy_manager.blacklist), 1)
        self.assertNotIn("expired.proxy:8080", proxy_manager.blacklist)
        self.assertIn("valid.proxy:8080", proxy_manager.blacklist)

    def test_save_blacklist(self):
        """Test _save_blacklist saves blacklist correctly"""
        # Set up a blacklist entry
        self.proxy_manager.blacklist = {"test.proxy:8080": str(datetime.now().timestamp())}

        # Save blacklist
        self.proxy_manager._save_blacklist()

        # Verify file was created and contains correct data
        with open(self.temp_blacklist.name, "r") as f:
            loaded_data = json.load(f)

        self.assertIn("test.proxy:8080", loaded_data)
        # Reason is not stored with timestamp in the new format
        # self.assertEqual(loaded_data["test.proxy:8080"]["reason"], "Test reason")
        self.assertIn("test.proxy:8080", loaded_data)  # Verify key exists

    def test_get_working_proxies_from_cache(self):
        """Test get_working_proxies returns cached proxies if available"""
        # Setup cached proxies
        test_proxies = ["192.168.1.1:8080", "192.168.1.2:8080"]
        self.proxy_manager.proxy_list = list(test_proxies)  # Ensure it's a new list instance
        self.proxy_manager.last_refresh = datetime.now().timestamp()

        # Patch the get_proxy_list method on the fp instance of self.proxy_manager
        with patch.object(self.proxy_manager.fp, "get_proxy_list") as mock_fp_get_proxy_list:
            # Call method
            proxies = asyncio.run(self.proxy_manager.get_working_proxies())

            # Verify cached proxies are returned
            self.assertEqual(proxies, test_proxies)
            # Verify that FreeProxy's get_proxy_list was not called because cache should be hit
            mock_fp_get_proxy_list.assert_not_called()

    @patch("google_scholar_scraper.proxy_manager.ProxyManager._test_proxy", new_callable=AsyncMock)  # Mock _test_proxy method
    def test_get_working_proxies_refresh(self, mock_test_proxy):
        """Test get_working_proxies refreshes proxies when needed"""
        # Force refresh by setting last_refresh to old timestamp
        self.proxy_manager.last_refresh = (
            datetime.now() - timedelta(seconds=self.proxy_manager.refresh_interval + 10)
        ).timestamp()

        raw_proxies_to_fetch = ["1.1.1.1:8080", "2.2.2.2:8080", "3.3.3.3:8080"]

        # Mock _test_proxy to simulate which raw proxies are working
        # _test_proxy should return the proxy string if working, None otherwise
        mock_test_proxy.side_effect = [
            raw_proxies_to_fetch[0],  # First proxy works
            None,  # Second proxy fails
            raw_proxies_to_fetch[2],  # Third proxy works
        ]

        # Patch the get_proxy_list method on the fp instance of self.proxy_manager
        with patch.object(self.proxy_manager.fp, "get_proxy_list", return_value=raw_proxies_to_fetch) as mock_fp_get_proxy_list:
            # Call method
            proxies = asyncio.run(self.proxy_manager.get_working_proxies())

            # Verify results
            expected_working_proxies = [raw_proxies_to_fetch[0], raw_proxies_to_fetch[2]]
            self.assertEqual(len(proxies), len(expected_working_proxies))
            for p in expected_working_proxies:
                self.assertIn(p, proxies)
            self.assertNotIn(raw_proxies_to_fetch[1], proxies)  # The failed proxy

            # Verify FreeProxy's get_proxy_list was called
            mock_fp_get_proxy_list.assert_called_once_with(repeat=True)

            # Verify _test_proxy was called for each raw proxy
            self.assertEqual(mock_test_proxy.call_count, len(raw_proxies_to_fetch))
            mock_test_proxy.assert_any_call(raw_proxies_to_fetch[0])
            mock_test_proxy.assert_any_call(raw_proxies_to_fetch[1])
            mock_test_proxy.assert_any_call(raw_proxies_to_fetch[2])

    def test_remove_proxy(self):
        """Test remove_proxy removes and blacklists a proxy"""
        # Setup test proxy
        test_proxy = "192.168.1.1:8080"
        self.proxy_manager.proxy_list = [test_proxy, "192.168.1.2:8080"]  # Changed to proxy_list

        # Remove proxy
        self.proxy_manager.remove_proxy(test_proxy)  # Removed reason argument

        # Verify proxy removed from active list
        self.assertNotIn(test_proxy, self.proxy_manager.proxy_list)  # Changed to proxy_list

        # Verify proxy added to blacklist
        self.assertIn(test_proxy, self.proxy_manager.blacklist)
        # self.assertEqual(self.proxy_manager.blacklist[test_proxy]["reason"], "Test reason") # Reason not stored this way

    def test_get_random_proxy_available(self):
        """Test get_random_proxy returns a random proxy when available"""
        # Setup test proxies
        test_proxies = ["192.168.1.1:8080", "192.168.1.2:8080"]
        self.proxy_manager.proxy_list = test_proxies  # Changed to proxy_list
        self.proxy_manager.last_refresh = datetime.now().timestamp()

        # Get random proxy
        proxy = asyncio.run(self.proxy_manager.get_random_proxy())

        # Verify a proxy was returned from the list
        self.assertIn(proxy, test_proxies)

    @patch("google_scholar_scraper.proxy_manager.ProxyManager.get_working_proxies", new_callable=AsyncMock)
    def test_get_random_proxy_none_available(self, mock_get_working_proxies):
        """Test get_random_proxy raises exception when no proxies available"""
        # Mock get_working_proxies to return empty list
        mock_get_working_proxies.return_value = []

        # Attempt to get random proxy and verify exception raised
        proxy = asyncio.run(self.proxy_manager.get_random_proxy())
        self.assertIsNone(proxy, "Expected None when no proxies are available after refresh attempts.")

    def test_mark_proxy_success(self):
        """Test mark_proxy_success updates proxy stats correctly"""
        # Setup test proxy
        test_proxy = "192.168.1.1:8080"
        self.proxy_manager._initialize_proxy_stats(test_proxy)

        # Mark success
        self.proxy_manager.mark_proxy_success(test_proxy)

        # Verify stats updated
        stats = self.proxy_manager.proxy_performance[test_proxy]  # Changed to proxy_performance
        self.assertEqual(stats["successes"], 1)  # Key is "successes" (plural)
        self.assertEqual(stats["failures"], 0)  # Key is "failures" (plural)
        # self.assertEqual(stats["success_rate"], 1.0) # success_rate is not stored/calculated

    def test_mark_proxy_failure(self):
        """Test mark_proxy_failure updates proxy stats correctly"""
        # Setup test proxy
        test_proxy = "192.168.1.1:8080"
        self.proxy_manager._initialize_proxy_stats(test_proxy)

        # Mark failure
        error_type = ProxyErrorType.CONNECTION
        self.proxy_manager.mark_proxy_failure(test_proxy, error_type)

        # Verify stats updated
        stats = self.proxy_manager.proxy_performance[test_proxy]  # Changed to proxy_performance
        self.assertEqual(stats["successes"], 0)  # Key is "successes" (plural)
        self.assertEqual(stats["failures"], 1)  # Key is "failures" (plural)
        # self.assertEqual(stats["success_rate"], 0.0) # success_rate is not stored/calculated
        self.assertEqual(stats["connection_errors"], 1)  # Check specific counter

    @pytest.mark.live_network  # Custom marker, needs to be registered in pytest config (e.g., pyproject.toml or pytest.ini)
    def test_internal_test_proxy_with_live_free_proxies(self):
        """
        Tests ProxyManager._test_proxy with a few live proxies from FreeProxy
        against a reliable external URL (https://example.com/).
        This is a network-dependent test and may be flaky.
        """
        # Ensure blacklist_file_name is defined in the scope of the finally block
        blacklist_file_name = None
        pm = None  # Ensure pm is defined for finally block

        try:
            with tempfile.NamedTemporaryFile(delete=False, mode="w", suffix=".json") as tmp_blacklist_file:
                tmp_blacklist_file.write("{}")  # Write empty JSON to make it valid
                blacklist_file_name = tmp_blacklist_file.name

            pm = ProxyManager(blacklist_file=blacklist_file_name)
            pm.test_url = "https://example.com/"  # Use a reliable, simple target

            fp = FreeProxy()
            try:
                live_proxies = fp.get_proxy_list(repeat=False)  # Get a single list of proxies
            except Exception as e:
                pytest.skip(f"FreeProxy().get_proxy_list() failed: {e}")  # Skip if FreeProxy itself errors out

            if not live_proxies:
                pytest.skip("FreeProxy returned no proxies to test.")

            num_to_test = min(len(live_proxies), 3)  # Test up to 3 proxies
            proxies_to_actually_test = live_proxies[:num_to_test]

            pm.logger.info(
                f"Attempting to test {len(proxies_to_actually_test)} live proxies against {pm.test_url}: {proxies_to_actually_test}"
            )

            success_count = 0
            failure_count = 0

            for proxy_candidate in proxies_to_actually_test:
                result = asyncio.run(pm._test_proxy(proxy_candidate))
                if result == proxy_candidate:
                    pm.logger.info(f"LIVE TEST: Proxy {proxy_candidate} WORKED against {pm.test_url}")
                    success_count += 1
                else:
                    pm.logger.warning(f"LIVE TEST: Proxy {proxy_candidate} FAILED against {pm.test_url} (result: {result})")
                    failure_count += 1

                self.assertTrue(
                    result == proxy_candidate or result is None,
                    f"Expected _test_proxy to return proxy string or None, got {result}",
                )

            pm.logger.info(
                f"Live proxy test summary: {success_count} worked, {failure_count} failed out of {num_to_test} tested."
            )

        finally:
            if blacklist_file_name and os.path.exists(blacklist_file_name):
                os.unlink(blacklist_file_name)
            # pm does not need explicit async closing here as _test_proxy manages its own session.

    # Intentionally keeping one blank line after the method, before if __name__


if __name__ == "__main__":
    unittest.main()
