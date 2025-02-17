import asyncio
import logging
import re
from typing import Optional

import hishel  # Import Hishel
import httpx
from parsel import Selector

from .exceptions import CaptchaException, NoProxiesAvailable
from .proxy_manager import ProxyManager
from .utils import detect_captcha, get_random_delay, get_random_user_agent

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(filename)s:%(lineno)d | %(funcName)s | %(message)s", level=logging.DEBUG
)


class Fetcher:
    def __init__(self, proxy_manager=None):
        self.proxy_manager = proxy_manager or ProxyManager()
        self.logger = logging.getLogger(__name__)
        self.client = self._create_client()  # Create cached client

    def _create_client(self):
        """Creates an httpx.AsyncClient with caching enabled."""
        transport = hishel.AsyncCacheTransport(transport=httpx.AsyncHTTPTransport())
        return hishel.AsyncCacheClient(transport=transport)

    async def fetch_page(self, url, retry_count=3, retry_delay=10):
        headers = {"User-Agent": get_random_user_agent()}
        proxy = self.proxy_manager.get_random_proxy()
        proxies = {"http://": f"http://{proxy}", "https://": f"https://{proxy}"} if proxy else None

        for attempt in range(retry_count):
            try:
                response = await self.client.get(url, headers=headers, proxies=proxies, timeout=10)
                response.raise_for_status()
                html_content = response.text
                if detect_captcha(html_content):
                    raise CaptchaException("CAPTCHA detected!")
                return html_content
            except (httpx.HTTPError, httpx.RequestError, asyncio.TimeoutError, CaptchaException, NoProxiesAvailable) as e:
                self.logger.warning(f"Attempt {attempt + 1} failed for {url}: {e}")
                if isinstance(e, NoProxiesAvailable):
                    self.logger.error(f"No proxies available: {e}")
                    return None
                if attempt == retry_count - 1:
                    self.logger.error(f"Failed to fetch {url} after {retry_count} attempts.")
                    return None
                if isinstance(e, CaptchaException):
                    self.logger.warning("CAPTCHA encountered, attempting to refresh proxy list.")
                else:
                    self.logger.info(f"Retrying in {retry_delay} seconds...")
                await asyncio.sleep(retry_delay)
                try:
                    await self.proxy_manager.get_working_proxies()
                except NoProxiesAvailable as e:
                    self.logger.error("Still no proxies available after refresh.")
                    return None
                proxy = self.proxy_manager.get_random_proxy()
                proxies = {"http://": f"http://{proxy}", "https://": f"https://{proxy}"} if proxy else None

            finally:
                await asyncio.sleep(get_random_delay())

    async def fetch_pages(self, urls):
        tasks = [self.fetch_page(url) for url in urls]
        return await asyncio.gather(*tasks)

    async def download_pdf(self, url, filename):
        headers = {"User-Agent": get_random_user_agent()}
        proxy = self.proxy_manager.get_random_proxy()
        proxies = {"http://": f"http://{proxy}", "https://": f"https://{proxy}"} if proxy else None
        retries = 3
        for attempt in range(retries):
            try:
                response = await self.client.get(url, headers=headers, proxies=proxies, timeout=20)
                response.raise_for_status()
                if response.headers["Content-Type"] == "application/pdf":
                    with open(filename, "wb") as f:
                        f.write(response.content)
                    self.logger.info(f"Downloaded PDF to {filename}")
                    return True
                else:
                    self.logger.warning(f"URL did not return a PDF: {url}")
                    return False
            except (httpx.HTTPError, httpx.RequestError, asyncio.TimeoutError) as e:
                self.logger.warning(f"Attempt {attempt + 1} to download PDF failed: {e}")
                if attempt == retries - 1:
                    self.logger.error(f"Failed to download PDF after {retries} attempts.")
                    return False
                await asyncio.sleep(get_random_delay(10, 20))  # Longer delay
                try:
                    await self.proxy_manager.get_working_proxies()
                except NoProxiesAvailable as e:
                    self.logger.error("Still no proxies available after refresh.")
                    return False
                proxy = self.proxy_manager.get_random_proxy()
                proxies = {"http://": f"http://{proxy}", "https://": f"https://{proxy}"} if proxy else None

    async def scrape_pdf_link(self, doi: str) -> Optional[str]:
        # ... (The rest of scrape_pdf_link remains almost the same.
        #       Just use self.client for all httpx requests)
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
            "Referer": "https://scholar.google.com",
        }

        unpaywall_url = f"https://api.unpaywall.org/v2/{doi}?email=unpaywall@impactstory.org"

        try:
            pdf_url = None

            # --- Unpaywall Check ---
            response = await self.client.get(unpaywall_url, timeout=10)  # Use self.client
            response.raise_for_status()
            data = response.json()

            paper_url = data.get("doi_url")

            if data.get("is_oa"):
                self.logger.info(f"Paper is Open Access according to Unpaywall. DOI: {doi}")
            else:
                self.logger.info(f"Paper is NOT Open Access according to Unpaywall. DOI: {doi}")

            # Get final redirected URL
            response = await self.client.get(paper_url, headers=headers, follow_redirects=True, timeout=20)  # Use self.client
            response.raise_for_status()
            self.logger.info(f"Final URL after redirect: {response.url}")

            final_url = str(response.url)
            selector = Selector(text=response.text)

            # --- Meta Tag Check ---
            meta_pdf_url = selector.xpath("//meta[@name='citation_pdf_url']/@content").get()
            if meta_pdf_url:
                self.logger.info(f"Found PDF URL in meta tag: {meta_pdf_url}")
                return meta_pdf_url

            # --- Domain-Specific Link Checks ---
            for link in selector.xpath("//a"):
                href = link.xpath("@href").get()
                if not href:
                    continue

                # 1. Nature.com (Pattern 1)
                if "nature.com" in final_url:
                    match = re.search(r"/nature/journal/.+?/pdf/(.+?)\.pdf$", href)
                    if match:
                        pdf_url = httpx.URL(final_url).join(href).unicode_string()
                        self.logger.info(f"Found PDF URL (Nature.com Pattern 1): {pdf_url}")
                        return pdf_url

                    # 2. Nature.com (Pattern 2)
                    match = re.search(r"/articles/nmicrobiol\d+\.pdf$", href)
                    if match:
                        pdf_url = httpx.URL(final_url).join(href).unicode_string()
                        self.logger.info(f"Found PDF URL (Nature.com Pattern 2): {pdf_url}")
                        return pdf_url

                # 3. NEJM
                if "nejm.org" in final_url:
                    if link.xpath("@data-download-content").get() == "Article":
                        pdf_url = httpx.URL(final_url).join(href).unicode_string()
                        self.logger.info(f"Found PDF URL (NEJM): {pdf_url}")
                        return pdf_url

                # 4. Taylor & Francis Online
                if "tandfonline.com" in final_url:
                    match = re.search(r"/doi/pdf/10.+?needAccess=true", href, re.IGNORECASE)
                    if match:
                        pdf_url = httpx.URL(final_url).join(href).unicode_string()
                        self.logger.info(f"Found PDF URL (Taylor & Francis): {pdf_url}")
                        return pdf_url

                # 5. Centers for Disease Control (CDC)
                if "cdc.gov" in final_url:
                    if "noDecoration" == link.xpath("@class").get() and re.search(r"\.pdf$", href):
                        pdf_url = httpx.URL(final_url).join(href).unicode_string()
                        self.logger.info(f"Found PDF URL (CDC): {pdf_url}")
                        return pdf_url

                # 6. ScienceDirect
                if "sciencedirect.com" in final_url:
                    pdf_url_attribute = link.xpath("@pdfurl").get()
                    if pdf_url_attribute:
                        pdf_url = httpx.URL(final_url).join(pdf_url_attribute).unicode_string()
                        self.logger.info(f"Found PDF URL (ScienceDirect): {pdf_url}")
                        return pdf_url

            # 7. IEEE Explore (check within the entire page content)
            if "ieeexplore.ieee.org" in final_url:
                match = re.search(r'"pdfPath":"(.+?)\.pdf"', response.text)
                if match:
                    pdf_path = match.group(1) + ".pdf"
                    pdf_url = "https://ieeexplore.ieee.org" + pdf_path
                    self.logger.info(f"Found PDF URL (IEEE Explore): {pdf_url}")
                    return pdf_url

            # --- General PDF Pattern Check (Fallback) ---
            doi_last_3 = doi[-3:] if len(doi) >= 3 else doi
            PDF_PATTERNS = [
                ".pdf",
                "/pdf/",
                "pdf/",
                "download",
                "fulltext",
                "article",
                "viewer",
                "content/pdf",
                "/nature/journal",
                "/articles/",
                "/doi/pdf/",
            ]
            pdf_links = selector.css("a::attr(href)").getall()

            for link in pdf_links:
                if any(pattern in link.lower() for pattern in PDF_PATTERNS):
                    if doi_last_3 in link.lower():
                        pdf_url = httpx.URL(final_url).join(link).unicode_string()
                        self.logger.info(f"Found PDF link (General Pattern): {pdf_url}")
                        return str(pdf_url)

                    pdf_url = httpx.URL(final_url).join(link).unicode_string()
                    self.logger.info(f"Found PDF link (General Pattern): {pdf_url}")
                    return str(pdf_url)

            self.logger.warning("No PDF link found on the page.")
            return None

        except httpx.HTTPStatusError as e:
            self.logger.error(f"Unpaywall API error ({e.response.status_code}): {e}")
            if e.response.status_code == 404:
                self.logger.error(f"Paper with DOI {doi} not found by Unpaywall")
            return None

        except httpx.RequestError as e:
            self.logger.error(f"Request error: {e}")
            return None

        except Exception as e:
            self.logger.exception(f"An unexpected error occurred: {e}")
            return None

    async def fetch_cited_by_page(self, url, proxy_manager, depth, max_depth, graph_builder):
        if depth > max_depth:
            return

        self.logger.info(f"Fetching cited-by page (depth {depth}): {url}")
        html_content = await self.fetch_page(url)  # Reuse existing fetch_page
        if html_content:
            cited_by_results = self.parser.parse_results(html_content)
            for result in cited_by_results:
                # Add to graph
                graph_builder.add_citation(result["title"], url, result.get("cited_by_url"))
                if result.get("cited_by_url"):
                    await self.fetch_cited_by_page(result["cited_by_url"], proxy_manager, depth + 1, max_depth, graph_builder)
