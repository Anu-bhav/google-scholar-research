# fetcher.py
import asyncio
import logging
import os
import random
import re
import time
from typing import Dict, List, Optional

import aiohttp
from fake_useragent import UserAgent
from parsel import Selector
from tqdm import tqdm

from .exceptions import CaptchaException, NoProxiesAvailable, ParsingException
from .models import ProxyErrorType  # Import ProxyErrorType
from .parser import AuthorProfileParser, Parser  # Make sure AuthorProfileParser is still used if needed
from .proxy_manager import ProxyManager
from .query_builder import QueryBuilder
from .utils import detect_captcha, get_random_user_agent


class Fetcher:
    def __init__(self, proxy_manager=None, min_delay=2, max_delay=5, max_retries=3, rolling_window_size=20):
        """Initializes the Fetcher.

        Args:
            proxy_manager (ProxyManager, optional): Proxy manager instance. Defaults to a new ProxyManager().
            min_delay (int): Minimum delay between requests in seconds. Defaults to 2.
            max_delay (int): Maximum delay between requests in seconds. Defaults to 5.
            max_retries (int): Maximum number of retries for a failed request. Defaults to 3.
            rolling_window_size (int): Size of the rolling window for RPS calculation. Defaults to 20.

        """
        self.proxy_manager = proxy_manager or ProxyManager()
        self.logger = logging.getLogger(__name__)
        self.client: Optional[aiohttp.ClientSession] = None
        self.min_delay = min_delay
        self.max_delay = max_delay
        self.max_retries = max_retries
        self.parser = Parser()
        self.author_parser = AuthorProfileParser()  # Keep this if you are still using AuthorProfileParser
        # Statistics
        self.successful_requests = 0
        self.failed_requests = 0
        self.proxies_used = set()
        self.proxies_removed = 0
        self.pdfs_downloaded = 0
        self.request_times = []
        self.rolling_window_size = rolling_window_size
        self.start_time = None

    async def _create_client(self) -> aiohttp.ClientSession:
        """Creates an aiohttp ClientSession if it doesn't exist or is closed."""
        if self.client is None or self.client.closed:
            timeout = aiohttp.ClientTimeout(total=10)
            self.client = aiohttp.ClientSession(timeout=timeout)
        return self.client

    async def _get_delay(self) -> float:
        """Calculates a random delay before making a request."""
        return random.uniform(self.min_delay, self.max_delay)

    async def fetch_page(self, url: str, retry_count: Optional[int] = None) -> Optional[str]:
        """Fetches a page with retries using the same proxy until failure."""
        headers = {"User-Agent": get_random_user_agent()}
        retry_count = retry_count or self.max_retries
        await self._create_client()

        proxy = await self.proxy_manager.get_random_proxy()  # Get a proxy *once* per fetch_page call
        if not proxy:
            self.logger.error("No proxies available at start of fetch for URL: %s", url)
            return None  # Exit early if no proxy available initially
        proxy_url = f"http://{proxy}"
        self.proxies_used.add(proxy)

        for attempt in range(retry_count):
            try:
                delay = await self._get_delay()
                await asyncio.sleep(delay)
                request_start_time = time.monotonic()

                async with self.client.get(url, headers=headers, proxy=proxy_url, timeout=10) as response:
                    response.raise_for_status()
                    html_content = await response.text()
                    if detect_captcha(html_content):
                        raise CaptchaException("CAPTCHA detected!")

                    self.successful_requests += 1
                    request_end_time = time.monotonic()
                    self.request_times.append(request_end_time - request_start_time)
                    self.request_times = self.request_times[-self.rolling_window_size :]
                    self.proxy_manager.mark_proxy_success(proxy)  # Mark success after successful fetch
                    return html_content

            except (aiohttp.ClientError, asyncio.TimeoutError, CaptchaException) as e:
                self.failed_requests += 1
                self.logger.warning(f"Attempt {attempt + 1} failed for {url}: {type(e).__name__}: {e} with proxy {proxy}")

                if isinstance(e, CaptchaException):
                    self.proxy_manager.mark_proxy_failure(proxy, ProxyErrorType.CAPTCHA)
                    self.proxy_manager.remove_proxy(proxy)
                    self.proxies_removed += 1
                    try:
                        await self.proxy_manager.refresh_proxies()
                    except NoProxiesAvailable:
                        self.logger.error("No proxies available after CAPTCHA.")
                        return None
                    return None  # Immediately return None after CAPTCHA and proxy removal/refresh

                if isinstance(e, asyncio.TimeoutError):
                    self.proxy_manager.mark_proxy_failure(proxy, ProxyErrorType.TIMEOUT)
                elif isinstance(e, aiohttp.ClientProxyConnectionError):
                    self.proxy_manager.mark_proxy_failure(proxy, ProxyErrorType.CONNECTION)
                else:
                    self.proxy_manager.mark_proxy_failure(proxy, ProxyErrorType.OTHER)

                if attempt == retry_count - 1:
                    self.proxy_manager.remove_proxy(proxy)
                    self.proxies_removed += 1
                    self.logger.error(f"Failed to fetch {url} after {retry_count} attempts with proxy {proxy}.")
                    return None
                else:
                    await asyncio.sleep(random.uniform(2, 5))  # Wait a bit before retrying with the same proxy

            except NoProxiesAvailable:
                self.logger.error("No proxies available during fetching of %s", url)
                return None

    async def fetch_pages(self, urls: List[str]) -> List[Optional[str]]:
        """Fetches multiple pages concurrently, each potentially using a different proxy (initially chosen)."""
        await self._create_client()
        return await asyncio.gather(*[self.fetch_page(url) for url in urls])

    async def download_pdf(self, url: str, filename: str) -> bool:
        """Downloads a PDF file with retries and proxy management."""
        headers = {"User-Agent": get_random_user_agent()}
        retries = 3

        await self._create_client()

        proxy = await self.proxy_manager.get_random_proxy()
        proxy_url = f"http://{proxy}" if proxy else None

        for attempt in range(retries):
            try:
                async with self.client.get(url, headers=headers, proxy=proxy_url, timeout=20) as response:
                    response.raise_for_status()
                    if response.headers.get("Content-Type") == "application/pdf":
                        with open(filename, "wb") as f:
                            async for chunk in response.content.iter_chunked(1024):
                                f.write(chunk)
                        self.logger.info(f"Downloaded PDF to {filename}")
                        self.pdfs_downloaded += 1
                        self.proxy_manager.mark_proxy_success(proxy)  # Mark success on PDF download
                        return True
                    else:
                        self.logger.warning(f"URL did not return a PDF: {url}")
                        return False
            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                self.logger.warning(f"Attempt {attempt + 1} to download PDF failed: {type(e).__name__}: {e}")
                if isinstance(e, asyncio.TimeoutError):
                    self.proxy_manager.mark_proxy_failure(proxy, ProxyErrorType.TIMEOUT)
                elif isinstance(e, aiohttp.ClientProxyConnectionError):
                    self.proxy_manager.mark_proxy_failure(proxy, ProxyErrorType.CONNECTION)
                else:
                    self.proxy_manager.mark_proxy_failure(proxy, ProxyErrorType.OTHER)
                if proxy:
                    self.proxy_manager.remove_proxy(proxy)
                if attempt == retries - 1:
                    return False
                await asyncio.sleep(random.uniform(10, 20))
                try:
                    await self.proxy_manager.get_working_proxies()
                except NoProxiesAvailable:
                    return False
            except NoProxiesAvailable:
                return False

    async def scrape_pdf_link(self, doi: str) -> Optional[str]:
        """Scrapes a PDF link from a DOI using Unpaywall and direct scraping."""
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
            "Referer": "https://scholar.google.com",
        }
        unpaywall_url = f"https://api.unpaywall.org/v2/{doi}?email=unpaywall@impactstory.org"

        await self._create_client()

        try:
            pdf_url = None
            async with self.client.get(unpaywall_url, timeout=10) as response:
                response.raise_for_status()
                data = await response.json()
                paper_url = data.get("doi_url")
                if data.get("is_oa"):
                    self.logger.info(f"Paper is Open Access according to Unpaywall. DOI: {doi}")
                else:
                    self.logger.info(f"Paper is NOT Open Access according to Unpaywall. DOI: {doi}")

                async with self.client.get(paper_url, headers=headers, timeout=20) as response:
                    response.raise_for_status()
                    self.logger.info(f"Final URL after redirect: {response.url}")
                    final_url = str(response.url)
                    selector = Selector(text=await response.text())
                    meta_pdf_url = selector.xpath("//meta[@name='citation_pdf_url']/@content").get()
                    if meta_pdf_url:
                        self.logger.info(f"Found PDF URL in meta tag: {meta_pdf_url}")
                        return meta_pdf_url

                    # The rest of your scraping logic using aiohttp-compatible methods
                    for link in selector.xpath("//a"):
                        href = link.xpath("@href").get()
                        if not href:
                            continue
                        if "nature.com" in final_url:
                            match = re.search(r"/nature/journal/.+?/pdf/(.+?)\.pdf$", href)
                            if match:
                                pdf_url = str(response.url.join(href))
                                return pdf_url
                            match = re.search(r"/articles/nmicrobiol\d+\.pdf$", href)
                            if match:
                                pdf_url = str(response.url.join(href))
                                return pdf_url
                        if "nejm.org" in final_url:
                            if link.xpath("@data-download-content").get() == "Article":
                                pdf_url = str(response.url.join(href))
                                return pdf_url
                        if "tandfonline.com" in final_url:
                            match = re.search(r"/doi/pdf/10.+?needAccess=true", href, re.IGNORECASE)
                            if match:
                                pdf_url = str(response.url.join(href))
                                return pdf_url
                        if "cdc.gov" in final_url:
                            if "noDecoration" == link.xpath("@class").get() and re.search(r"\.pdf$", href):
                                pdf_url = str(response.url.join(href))
                                return pdf_url
                        if "sciencedirect.com" in final_url:
                            pdf_url_attribute = link.xpath("@pdfurl").get()
                            if pdf_url_attribute:
                                pdf_url = str(response.url.join(pdf_url_attribute))
                                return pdf_url

                    if "ieeexplore.ieee.org" in final_url:
                        match = re.search(r'"pdfPath":"(.+?)\.pdf"', await response.text())
                        if match:
                            pdf_path = match.group(1) + ".pdf"
                            pdf_url = "https://ieeexplore.ieee.org" + pdf_path
                            return pdf_url

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
                                pdf_url = str(response.url.join(link))
                                return str(pdf_url)
                            pdf_url = str(response.url.join(link))
                            return str(pdf_url)

                    return None

        except aiohttp.ClientResponseError as e:
            if e.status == 404:
                self.logger.error(f"Paper with DOI {doi} not found by Unpaywall")
            return None
        except aiohttp.ClientError as e:
            return None
        except Exception as e:
            self.logger.exception(f"An unexpected error occurred: {e}")
            return None

    async def extract_cited_title(self, cited_by_url):
        """Extracts the title of the cited paper from the cited-by URL."""
        if not cited_by_url:
            return None
        try:
            html_content = await self.fetch_page(cited_by_url)
            if html_content:
                selector = Selector(text=html_content)
                first_result = selector.css("div.gs_ri h3.gs_rt")
                if first_result:
                    return self.parser.extract_title(first_result)
        except Exception as e:
            self.logger.error(f"Error extracting cited title from {cited_by_url}: {e}")
        return "Unknown Title"

    async def fetch_cited_by_page(self, url, proxy_manager, depth, max_depth, graph_builder):
        """Recursively fetches and parses cited-by pages to build a citation graph."""
        if depth > max_depth:
            return []

        self.logger.info(f"Fetching cited-by page (depth {depth}): {url}")
        html_content = await self.fetch_page(url)
        tasks = []
        if html_content:
            try:
                cited_by_results = self.parser.parse_results(html_content)
                for result in cited_by_results:
                    cited_title = await self.extract_cited_title(result.get("cited_by_url"))
                    graph_builder.add_citation(result["title"], url, result.get("cited_by_url"), cited_title)

                    if result.get("cited_by_url") and depth + 1 <= max_depth:
                        tasks.append(
                            self.fetch_cited_by_page(result["cited_by_url"], proxy_manager, depth + 1, max_depth, graph_builder)
                        )
            except ParsingException as e:
                self.logger.error(f"Error parsing cited-by page: {e}")
        return tasks

    async def close(self):
        """Closes the aiohttp ClientSession."""
        if self.client and not self.client.closed:
            await self.client.close()

    def calculate_rps(self):
        """Calculates the rolling average of requests per second."""
        if len(self.request_times) < 2:
            return 0
        total_time = self.request_times[-1] - self.request_times[0]
        if total_time == 0:
            return 0
        return (len(self.request_times) - 1) / total_time

    def calculate_etr(self, rps, total_results, results_collected):
        """Calculates the estimated time remaining."""
        if rps == 0:
            return None
        remaining_results = total_results - results_collected
        if remaining_results <= 0:
            return 0
        return remaining_results / rps

    async def scrape(
        self,
        query,
        authors,
        publication,
        year_low,
        year_high,
        num_results,
        pdf_dir,
        max_depth,
        graph_builder,
        data_handler,
        phrase=None,
        exclude=None,
        title=None,
        author=None,
        source=None,
    ):
        """Scrapes Google Scholar search results and related information.

        Args:
            query (str): The main search query.
            authors (str, optional): Search for specific authors.
            publication (str, optional): Search within a specific publication.
            year_low (int, optional): Lower bound of the publication year range.
            year_high (int, optional): Upper bound of the publication year range.
            num_results (int): Maximum number of results to scrape.
            pdf_dir (str): Directory to save downloaded PDFs.
            max_depth (int): Maximum depth for recursive citation scraping.
            graph_builder (GraphBuilder): Graph builder instance for citation graph.
            data_handler (DataHandler): Data handler instance for database operations.
            phrase (str, optional): Search for an exact phrase.
            exclude (str, optional): Keywords to exclude (comma-separated).
            title (str, optional): Search within the title.
            author (str, optional): Search within the author field.
            source (str, optional): Search within the source (publication).

        Returns:
            List[dict]: A list of scraped results.

        """
        all_results = []
        start_index = 0
        query_builder = QueryBuilder()

        await self._create_client()
        self.start_time = time.monotonic()

        with tqdm(total=num_results, desc="Scraping Results", unit="result") as pbar:
            while len(all_results) < num_results:
                url = query_builder.build_url(
                    query, start_index, authors, publication, year_low, year_high, phrase, exclude, title, author, source
                )

                if await data_handler.result_exists(url):
                    start_index += 10
                    continue

                html_content = await self.fetch_page(url)
                if not html_content:
                    start_index += 10
                    continue

                try:
                    parsed_results_with_items = list(
                        zip(self.parser.parse_results(html_content, True), self.parser.parse_raw_items(html_content))
                    )
                    results = [result_item[0] for result_item in parsed_results_with_items]
                    raw_items = [result_item[1] for result_item in parsed_results_with_items]
                    if not results:
                        break

                    citation_tasks = []
                    for item, result in zip(raw_items, results):
                        pdf_url = None
                        if result.get("doi"):
                            pdf_url = await self.scrape_pdf_link(result["doi"])  # Directly use scrape_pdf_link with DOI

                        if pdf_url:  # Only proceed if pdf_url is found by scrape_pdf_link
                            result["pdf_url"] = pdf_url
                            safe_title = re.sub(r'[\\/*?:"<>|]', "", result["title"])
                            pdf_filename = os.path.join(
                                pdf_dir, f"{safe_title}_{result.get('publication_info', {}).get('year', 'unknown')}.pdf"
                            )
                            if await self.download_pdf(pdf_url, pdf_filename):
                                result["pdf_path"] = pdf_filename
                        await data_handler.insert_result(result)

                        cited_title = await self.extract_cited_title(result.get("cited_by_url"))
                        graph_builder.add_citation(
                            result["title"], result["article_url"], result.get("cited_by_url"), cited_title
                        )
                        if result.get("cited_by_url"):
                            citation_tasks.append(
                                self.fetch_cited_by_page(result["cited_by_url"], self.proxy_manager, 1, max_depth, graph_builder)
                            )

                    nested_tasks = await asyncio.gather(*citation_tasks)
                    flat_tasks = [task for sublist in nested_tasks for task in sublist]
                    while flat_tasks:
                        next_level_tasks = await asyncio.gather(*flat_tasks)
                        flat_tasks = [task for sublist in next_level_tasks for task in sublist]

                    pbar.update(len(results))

                    rps = self.calculate_rps()
                    elapsed_time = time.monotonic() - self.start_time
                    etr = self.calculate_etr(rps, num_results, len(all_results))

                    pbar.set_postfix({
                        "RPS": f"{rps:.2f}",
                        "Success": self.successful_requests,
                        "Failed": self.failed_requests,
                        "Proxies Used": len(self.proxies_used),
                        "Proxies Removed": self.proxies_removed,
                        "PDFs": self.pdfs_downloaded,
                        "Elapsed": f"{elapsed_time:.2f}s",
                        "ETR": f"{etr:.2f}s" if etr is not None else "N/A",
                    })

                    all_results.extend(results)
                    next_page = self.parser.find_next_page(html_content)
                    if next_page:
                        start_index += 10
                    else:
                        break
                except ParsingException as e:
                    start_index += 10
                    continue

        return all_results[:num_results]

    async def fetch_author_profile(self, author_id: str):
        """Fetches and parses an author's profile page."""
        url = QueryBuilder().build_author_profile_url(author_id)
        html_content = await self.fetch_page(url)
        if html_content:
            try:
                author_data = self.author_parser.parse_profile(html_content)
                return author_data
            except ParsingException as e:
                self.logger.error(f"Error parsing author profile: {e}")
                return None
        return None

    async def scrape_publication_details(self, publication_url: str) -> Optional[List[Dict]]:
        """Scrapes details for a single publication URL (e.g., from author profile).

        Fetches the publication page and uses the parser to extract results.
        Returns a list of parsed results (usually a list of one, but parser returns a list).
        """
        html_content = await self.fetch_page(publication_url)  # Reuse fetch_page for proxy and retry logic
        if html_content:
            try:
                publication_details = self.parser.parse_results(html_content)  # Reuse parser
                return publication_details  # Returns a list of dicts
            except ParsingException as e:
                self.logger.error(f"Error parsing publication details from {publication_url}: {e}")
                return None
        return None
