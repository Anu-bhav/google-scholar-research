# proxy_manager.py
import asyncio
import logging
import random
import time
import urllib.parse
from typing import List, Optional

import aiohttp
from exceptions import NoProxiesAvailable
from fp.fp import FreeProxy
from models import ProxyErrorType


class ProxyManager:
    def __init__(self, timeout=5, refresh_interval=300, blacklist_duration=600, num_proxies=20):
        self.logger = logging.getLogger(__name__)
        self.fp = FreeProxy()
        self.proxy_list = []
        self.blacklist = {}  # {proxy: timestamp}
        self.refresh_interval = refresh_interval
        self.blacklist_duration = blacklist_duration
        self.last_refresh = 0
        self.num_proxies = num_proxies
        self.timeout = timeout
        self.test_url = "https://scholar.google.com/"  # Test with Google Scholar

    async def _test_proxy(self, proxy: str) -> Optional[str]:
        """Test if a proxy is working using aiohttp and CONNECT."""
        if proxy in self.blacklist and time.time() - self.blacklist[proxy] < self.blacklist_duration:
            return None

        proxy_url = f"http://{proxy}"
        timeout = aiohttp.ClientTimeout(total=self.timeout)
        connect_url = self.test_url
        parsed_url = urllib.parse.urlparse(connect_url)
        connect_host = parsed_url.hostname
        connect_port = parsed_url.port if parsed_url.port else 443

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
                            self.logger.info(f"Successfully fetched {connect_url} using proxy: {proxy}")
                            return proxy  # Return just the proxy (no latency)

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
            return self.proxy_list

        raw_proxies = self.fp.get_proxy_list(repeat=True)
        self.logger.debug(f"Fetched proxies: {raw_proxies}")
        if not raw_proxies:
            self.logger.warning("No proxies found from FreeProxy.")
            raise NoProxiesAvailable("No raw proxies found.")

        tasks = [self._test_proxy(proxy) for proxy in raw_proxies]
        results = await asyncio.gather(*tasks)

        working_proxies = [proxy for proxy in results if proxy]  # Filter out None values
        self.proxy_list = working_proxies[: self.num_proxies]  # Limit to the first num_proxies
        self.last_refresh = time.time()

        if not self.proxy_list:
            self.logger.warning("No working proxies found.")
            raise NoProxiesAvailable("No working proxies found.")

        return self.proxy_list

    async def refresh_proxies(self):
        """Force refresh the proxy list."""
        await self.get_working_proxies()

    async def get_random_proxy(self) -> Optional[str]:
        """Return a random working proxy."""
        try:
            if not self.proxy_list:
                await self.refresh_proxies()
            return random.choice(self.proxy_list) if self.proxy_list else None
        except NoProxiesAvailable:
            return None

    def remove_proxy(self, proxy: str):
        """Remove a proxy and blacklist it."""
        if proxy in self.proxy_list:
            self.proxy_list.remove(proxy)
            self.blacklist[proxy] = time.time()
            self.logger.info(f"Removed proxy {proxy} and added to blacklist.")
