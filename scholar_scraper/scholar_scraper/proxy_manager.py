import asyncio
import json
import logging
import random
import time
import urllib.parse
from typing import Callable, List, Optional

import aiohttp
from fp.fp import FreeProxy

from .exceptions import NoProxiesAvailable
from .models import ProxyErrorType  # Make sure this import is correct based on your project structure


class ProxyManager:
    def __init__(
        self, timeout=5, refresh_interval=300, blacklist_duration=600, num_proxies=20, blacklist_file="proxy_blacklist.json"
    ):
        """Initializes the ProxyManager.

        Args:
            timeout (int): Timeout for proxy testing requests in seconds. Defaults to 5.
            refresh_interval (int): Interval in seconds to refresh the proxy list. Defaults to 300 (5 minutes).
            blacklist_duration (int): Duration in seconds to blacklist a proxy after failure. Defaults to 600 (10 minutes).
            num_proxies (int): Number of working proxies to keep in the list. Defaults to 20.
            blacklist_file (str): Filename for persistent blacklist JSON file. Defaults to "proxy_blacklist.json".

        """
        self.logger = logging.getLogger(__name__)
        self.fp = FreeProxy()
        self.proxy_list = []
        self.blacklist = {}
        self.blacklist_file = blacklist_file
        self._load_blacklist()  # Load blacklist from file at initialization
        self.refresh_interval = refresh_interval
        self.blacklist_duration = blacklist_duration
        self.last_refresh = 0
        self.num_proxies = num_proxies
        self.timeout = timeout
        self.test_url = "https://scholar.google.com/"

        # Proxy Performance Monitoring Data
        self.proxy_performance = {}  # {proxy: {successes: int, failures: int, timeouts: int, captchas: int, connection_errors: int, last_latency: float, request_count: int, last_used: float}}

    def _load_blacklist(self):
        """Loads the blacklist from a JSON file."""
        try:
            with open(self.blacklist_file, "r") as f:
                self.blacklist = json.load(f)
                # Ensure timestamps are still valid and convert to float
                current_time = time.time()
                self.blacklist = {
                    proxy: ts for proxy, ts in self.blacklist.items() if current_time - float(ts) < self.blacklist_duration
                }
        except FileNotFoundError:
            self.blacklist = {}  # Start with an empty blacklist if file not found
        except json.JSONDecodeError:
            self.logger.warning(f"Blacklist file {self.blacklist_file} corrupted. Starting with an empty blacklist.")
            self.blacklist = {}

    def _save_blacklist(self):
        """Saves the blacklist to a JSON file."""
        try:
            with open(self.blacklist_file, "w") as f:
                json.dump(self.blacklist, f)
        except Exception as e:
            self.logger.error(f"Error saving blacklist to file {self.blacklist_file}: {e}")

    def _initialize_proxy_stats(self, proxy: str):
        """Initializes performance stats for a new proxy."""
        if proxy not in self.proxy_performance:
            self.proxy_performance[proxy] = {
                "successes": 0,
                "failures": 0,
                "timeouts": 0,
                "captchas": 0,
                "connection_errors": 0,
                "last_latency": 0.0,
                "request_count": 0,
                "last_used": 0.0,
            }

    async def _test_proxy(self, proxy: str) -> Optional[str]:
        """Test if a proxy is working using aiohttp and CONNECT, and measure latency."""
        if proxy in self.blacklist and time.time() - float(self.blacklist[proxy]) < self.blacklist_duration:
            return None  # Proxy is blacklisted and within blacklist duration

        proxy_url = f"http://{proxy}"
        timeout = aiohttp.ClientTimeout(total=self.timeout)
        connect_url = self.test_url
        parsed_url = urllib.parse.urlparse(connect_url)
        connect_host = parsed_url.hostname
        connect_port = parsed_url.port if parsed_url.port else 443

        self._initialize_proxy_stats(proxy)  # Initialize stats when testing a proxy

        start_time = time.monotonic()  # Start time for latency measurement

        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                try:
                    async with session.request(
                        "CONNECT",
                        f"http://{connect_host}:{connect_port}",
                        proxy=proxy_url,
                        headers={"Host": connect_host},
                    ) as conn_response:
                        conn_response.raise_for_status()
                        self.logger.debug(f"CONNECT tunnel established via {proxy}")

                        async with session.get(
                            connect_url,
                            ssl=True,
                            headers={"Host": connect_host},
                        ) as get_response:
                            get_response.raise_for_status()
                            end_time = time.monotonic()  # End time for latency measurement
                            latency = end_time - start_time
                            self.proxy_performance[proxy]["last_latency"] = latency  # Record latency
                            self.logger.info(f"Successfully fetched {connect_url} using proxy: {proxy} (Latency: {latency:.2f}s)")
                            return proxy  # Return just the proxy

                except aiohttp.ClientProxyConnectionError as e:
                    self.logger.debug(f"Proxy connection error: {e}")
                except aiohttp.ClientResponseError as e:
                    self.logger.debug(f"HTTP error after CONNECT: {e.status} - {e.message}")
                except Exception as e:
                    self.logger.debug(f"Error during CONNECT: {type(e).__name__}: {e}")
        except Exception as e:
            self.logger.debug(f"Error testing proxy {proxy}: {type(e).__name__}: {e}")

        return None

    async def get_working_proxies(self) -> List[str]:
        """Fetch, test, and return a list of working proxies."""
        current_time = time.time()
        if current_time - self.last_refresh < self.refresh_interval and self.proxy_list:
            return self.proxy_list  # Return cached proxies if within refresh interval

        raw_proxies = self.fp.get_proxy_list(repeat=True)
        self.logger.debug(f"Fetched {len(raw_proxies)} raw proxies from FreeProxy.")
        if not raw_proxies:
            self.logger.warning("No proxies found from FreeProxy.")
            raise NoProxiesAvailable("No raw proxies found.")

        tasks = [self._test_proxy(proxy) for proxy in raw_proxies]
        results = await asyncio.gather(*tasks)

        working_proxies = [proxy for proxy in results if proxy]  # Filter out None values
        self.proxy_list = working_proxies[: self.num_proxies]  # Limit to the first num_proxies
        self.last_refresh = time.time()

        # Initialize stats for newly added proxies in proxy_list after refresh
        for proxy in self.proxy_list:
            self._initialize_proxy_stats(proxy)

        if not self.proxy_list:
            self.logger.warning("No working proxies found after testing.")
            raise NoProxiesAvailable("No working proxies found.")

        self.logger.info(f"Refreshed proxy list. Found {len(self.proxy_list)} working proxies.")
        return self.proxy_list

    async def refresh_proxies(self):
        """Force refresh the proxy list."""
        await self.get_working_proxies()

    async def get_random_proxy(self) -> Optional[str]:
        """Return a random working proxy, updating usage stats."""
        try:
            if not self.proxy_list:
                if time.time() - self.last_refresh > self.refresh_interval:
                    await self.refresh_proxies()
                elif not self.proxy_list:  # Check again after normal condition, if still empty, force refresh
                    self.logger.warning("Proxy list is empty after normal refresh interval, forcing refresh...")
                    await self.refresh_proxies()
                if not self.proxy_list:  # Double check if list is still empty after refresh attempts.
                    raise NoProxiesAvailable("No working proxies available after refresh.")

            if self.proxy_list:
                proxy = random.choice(self.proxy_list)
                self.proxy_performance[proxy]["last_used"] = time.time()  # Record last used time
                self.proxy_performance[proxy]["request_count"] += 1  # Increment request count
                return proxy
            return None
        except NoProxiesAvailable:
            return None

    def remove_proxy(self, proxy: str):
        """Remove a proxy from the working list and blacklist it."""
        if proxy in self.proxy_list:
            self.proxy_list.remove(proxy)
            self.blacklist[proxy] = str(time.time())  # Store timestamp as string for JSON compatibility
            self.logger.info(f"Removed proxy {proxy} and added to blacklist.")
            self._save_blacklist()  # Save blacklist after removing proxy

    def mark_proxy_failure(self, proxy: str, error_type: ProxyErrorType):
        """Mark a proxy as failed and record the error type."""
        if proxy and proxy in self.proxy_performance:  # Ensure proxy is not None and in performance data
            self.proxy_performance[proxy]["failures"] += 1
            if error_type == ProxyErrorType.TIMEOUT:
                self.proxy_performance[proxy]["timeouts"] += 1
            elif error_type == ProxyErrorType.CAPTCHA:
                self.proxy_performance[proxy]["captchas"] += 1
            elif error_type == ProxyErrorType.CONNECTION:
                self.proxy_performance[proxy]["connection_errors"] += 1
            else:  # ProxyErrorType.OTHER or unexpected cases
                pass  # Failures count is already incremented

    def mark_proxy_success(self, proxy: str):
        """Mark a proxy as successful."""
        if proxy and proxy in self.proxy_performance:  # Ensure proxy is not None and in performance data
            self.proxy_performance[proxy]["successes"] += 1

    def get_proxy_performance_data(self) -> dict:
        """Returns the proxy performance data."""
        return self.proxy_performance

    def log_proxy_performance(self):
        """Logs the proxy performance data to the logger."""
        self.logger.info("--- Proxy Performance Report ---")
        for proxy, stats in self.proxy_performance.items():
            total_requests = stats["successes"] + stats["failures"]
            success_rate = (stats["successes"] / total_requests * 100) if total_requests > 0 else 0
            report_str = (
                f"Proxy: {proxy} | Success Rate: {success_rate:.2f}% | "
                f"Successes: {stats['successes']} | Failures: {stats['failures']} | "
                f"Timeouts: {stats['timeouts']} | CAPTCHAs: {stats['captchas']} | Connection Errors: {stats['connection_errors']} | "
                f"Avg Latency: {stats['last_latency']:.2f}s | Requests: {stats['request_count']} | Last Used: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(stats['last_used'])) if stats['last_used'] else 'Never'}"
            )
            self.logger.info(report_str)
        self.logger.info("--- End Proxy Performance Report ---")
