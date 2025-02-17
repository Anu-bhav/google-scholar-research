# scholar_scraper/scholar_scraper/proxy_manager.py
from free_proxy import FreeProxy
import asyncio
import httpx  # Changed from aiohttp to httpx
import logging
from .exceptions import NoProxiesAvailable
import random

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")


class ProxyManager:
    def __init__(self, country_id=None, timeout=0.5, https=True, check_anonymity=True):
        self.fp = FreeProxy(country_id=country_id, timeout=timeout, https=https, rand=True)
        self.proxy_list = []
        self.check_anonymity = check_anonymity
        self.logger = logging.getLogger(__name__)

    async def _test_proxy(self, proxy, session):  # session is httpx.AsyncClient now
        """Tests a single proxy for speed and anonymity."""
        test_url = "https://www.google.com"  # Use a reliable test URL
        try:
            start_time = asyncio.get_event_loop().time()
            response = await session.get(
                test_url, proxies={"http": f"http://{proxy}", "https": f"https://{proxy}"}, timeout=5
            )  # httpx proxies format
            response.raise_for_status()  # Check for HTTP errors
            end_time = asyncio.get_event_loop().time()
            latency = end_time - start_time

            if self.check_anonymity:
                # Basic anonymity check (can be improved with dedicated APIs)
                if "X-Forwarded-For" in response.headers or "Via" in response.headers:
                    anonymity = "Transparent"
                else:
                    anonymity = "Anonymous"  # Could also be Elite, but hard to distinguish
            else:
                anonymity = "Unknown"
            return proxy, latency, anonymity

        except (httpx.HTTPError, httpx.RequestError, asyncio.TimeoutError) as e:  # httpx errors
            # self.logger.debug(f"Proxy {proxy} failed: {e}") # Log at debug level
            return None, None, None

    async def get_working_proxies(self, num_proxies=10):
        """Gets a list of working proxies, testing for speed and anonymity."""
        raw_proxies = self.fp.get_proxy_list()
        if not raw_proxies:
            raise NoProxiesAvailable("No raw proxies found from free-proxy.")

        working_proxies = []
        async with httpx.AsyncClient() as session:  # httpx AsyncClient
            tasks = [self._test_proxy(proxy, session) for proxy in raw_proxies]
            results = await asyncio.gather(*tasks)

            for proxy, latency, anonymity in results:
                if proxy:  # If the proxy test was successful
                    working_proxies.append((proxy, latency, anonymity))

        # Sort by latency (fastest first)
        working_proxies.sort(key=lambda x: x[1])
        self.proxy_list = [p[0] for p in working_proxies[:num_proxies]]  # Store only proxy string
        self.logger.info(f"Found {len(self.proxy_list)} working proxies.")
        if not self.proxy_list:
            raise NoProxiesAvailable("No working proxies found after testing")
        return self.proxy_list

    def get_random_proxy(self):
        if self.proxy_list:
            return random.choice(self.proxy_list)
        return None
