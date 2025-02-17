# scholar_scraper/scholar_scraper/proxy_manager.py
import asyncio
import logging
import random

import httpx
import httpx_caching  # Import the library
from fp.fp import FreeProxy

from .exceptions import NoProxiesAvailable

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")


class ProxyManager:
    def __init__(self, country_id=None, timeout=0.5, https=True, check_anonymity=True):
        self.fp = FreeProxy(country_id=country_id, timeout=timeout, https=https, rand=True)
        self.proxy_list = []
        self.check_anonymity = check_anonymity
        self.logger = logging.getLogger(__name__)
        self.client = self._create_client()  # Create a cached client here as well

    def _create_client(self):
        """Creates an httpx.AsyncClient with caching enabled."""
        return httpx_caching.AsyncClient(
            mounts={"https://": httpx_caching.AsyncCacheControl(cacheable_methods=["GET"]), "http://": httpx.AsyncTransport()},
            cache=httpx_caching.FileCache(cache_dir="proxy_http_cache"),
        )

    async def _test_proxy(self, proxy):  # No session argument needed
        """Tests a single proxy for speed and anonymity."""
        test_url = "https://www.google.com"
        try:
            start_time = asyncio.get_event_loop().time()
            response = await self.client.get(
                test_url, proxies={"http://": f"http://{proxy}", "https://": f"https://{proxy}"}, timeout=5
            )  # Use self.client
            response.raise_for_status()
            end_time = asyncio.get_event_loop().time()
            latency = end_time - start_time

            if self.check_anonymity:
                if "X-Forwarded-For" in response.headers or "Via" in response.headers:
                    anonymity = "Transparent"
                else:
                    anonymity = "Anonymous"  # Could also be Elite, but hard to distinguish
            else:
                anonymity = "Unknown"
            return proxy, latency, anonymity

        except (httpx.HTTPError, httpx.RequestError, asyncio.TimeoutError) as e:
            return None, None, None

    async def get_working_proxies(self, num_proxies=10):
        """Gets a list of working proxies, testing for speed and anonymity."""
        raw_proxies = self.fp.get_proxy_list()
        if not raw_proxies:
            raise NoProxiesAvailable("No raw proxies found from free-proxy.")

        working_proxies = []
        tasks = [self._test_proxy(proxy) for proxy in raw_proxies]  # No session needed
        results = await asyncio.gather(*tasks)

        for proxy, latency, anonymity in results:
            if proxy:
                working_proxies.append((proxy, latency, anonymity))

        working_proxies.sort(key=lambda x: x[1])
        self.proxy_list = [p[0] for p in working_proxies[:num_proxies]]
        self.logger.info(f"Found {len(self.proxy_list)} working proxies.")
        if not self.proxy_list:
            raise NoProxiesAvailable("No working proxies found after testing")
        return self.proxy_list

    def get_random_proxy(self):
        if self.proxy_list:
            return random.choice(self.proxy_list)
        return None
