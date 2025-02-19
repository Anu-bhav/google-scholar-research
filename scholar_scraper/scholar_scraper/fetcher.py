# fetcher.py
import asyncio
import logging
import random
import time
from parser import AuthorProfileParser, Parser  # Import the parsers
from typing import List, Optional

import aiohttp
from exceptions import CaptchaException, NoProxiesAvailable
from models import ProxyErrorType
from proxy_manager import ProxyManager
from tqdm import tqdm
from utils import get_random_user_agent


class Fetcher:
    def __init__(self, proxy_manager=None, min_delay=2, max_delay=5, max_retries=3, rolling_window_size=20):
        self.proxy_manager = proxy_manager or ProxyManager()
        self.logger = logging.getLogger(__name__)
        self.client: Optional[aiohttp.ClientSession] = None
        self.min_delay = min_delay
        self.max_delay = max_delay
        self.max_retries = max_retries
        self.parser = Parser()
        self.author_parser = AuthorProfileParser()  # Create an instance of AuthorProfileParser
        # Statistics
        self.successful_requests = 0
        self.failed_requests = 0
        self.proxies_used = set()
        self.proxies_removed = 0
        self.pdfs_downloaded = 0
        self.request_times = []  # Store last N request times for RPS calculation
        self.rolling_window_size = rolling_window_size
        self.start_time = None

    async def _create_client(self) -> aiohttp.ClientSession:
        """Creates an aiohttp ClientSession with a timeout."""
        if self.client is None or self.client.closed:
            timeout = aiohttp.ClientTimeout(total=10)  # Set a default timeout
            self.client = aiohttp.ClientSession(timeout=timeout)
        return self.client

    async def _get_delay(self) -> float:
        """Calculates the delay before making a request."""
        return random.uniform(self.min_delay, self.max_delay)

    async def fetch_page(self, url: str, retry_count: Optional[int] = None) -> Optional[str]:
        """Fetches a page with retries and immediate proxy rotation on failure."""
        headers = {"User-Agent": get_random_user_agent()}
        retry_count = retry_count or self.max_retries
        await self._create_client()

        for attempt in range(retry_count):
            proxy = await self.proxy_manager.get_random_proxy()
            proxy_url = f"http://{proxy}" if proxy else None

            try:
                delay = await self._get_delay()
                await asyncio.sleep(delay)  # Keep the general delay
                if proxy:
                    self.proxies_used.add(proxy)  # Track used proxies
                request_start_time = time.monotonic()  # Time before request

                async with self.client.get(url, headers=headers, proxy=proxy_url, timeout=10) as response:
                    response.raise_for_status()
                    html_content = await response.text()
                    if detect_captcha(html_content):
                        raise CaptchaException("CAPTCHA detected!")  # Still important

                    self.successful_requests += 1  # Increment successful requests
                    request_end_time = time.monotonic()
                    self.request_times.append(request_end_time - request_start_time)
                    # Keep only the last N request times
                    self.request_times = self.request_times[-self.rolling_window_size :]
                    return html_content

            except (aiohttp.ClientError, asyncio.TimeoutError, CaptchaException) as e:
                self.failed_requests += 1  # Increment failed requests
                self.logger.warning(f"Attempt {attempt + 1} failed for {url}: {type(e).__name__}: {e} with proxy {proxy}")

                if proxy:
                    self.proxy_manager.remove_proxy(proxy)
                    self.proxies_removed += 1

                if attempt == retry_count - 1:
                    self.logger.error(f"Failed to fetch {url} after {retry_count} attempts.")
                    return None

                # Immediate proxy rotation on *any* failure (except maybe a short timeout)
                if isinstance(e, asyncio.TimeoutError):
                    await asyncio.sleep(random.uniform(2, 5))  # short timeout.
                # No 'else' - rotate immediately for all other errors
                if isinstance(e, CaptchaException):  # Still handle CAPTCHA specially
                    try:
                        await self.proxy_manager.refresh_proxies()
                    except NoProxiesAvailable:
                        self.logger.error("No proxies available after CAPTCHA.")
                        return None

            except NoProxiesAvailable:  # Handles case where no proxies can be found at all.
                self.logger.error("No proxies available.")
                return None

    async def fetch_pages(self, urls: List[str]) -> List[Optional[str]]:
        """Fetches multiple pages concurrently."""
        await self._create_client()  # Ensure client session exists
        return await asyncio.gather(*[self.fetch_page(url) for url in urls])

    async def download_pdf(self, url: str, filename: str) -> bool:
        """Downloads a PDF file."""
        headers = {"User-Agent": get_random_user_agent()}
        retries = 3

        await self._create_client()  # Ensure client session exists

        for attempt in range(retries):
            proxy = await self.proxy_manager.get_random_proxy()  # Await, it's async now
            proxy_url = f"http://{proxy}" if proxy else None

            try:
                async with self.client.get(url, headers=headers, proxy=proxy_url, timeout=20) as response:
                    response.raise_for_status()
                    if response.headers.get("Content-Type") == "application/pdf":
                        with open(filename, "wb") as f:
                            async for chunk in response.content.iter_chunked(1024):  # Iterate over the content
                                f.write(chunk)
                        self.logger.info(f"Downloaded PDF to {filename}")
                        self.pdfs_downloaded += 1  # Increment PDFs downloaded
                        return True
                    else:
                        self.logger.warning(f"URL did not return a PDF: {url}")
                        return False
            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                self.logger.warning(f"Attempt {attempt + 1} to download PDF failed: {type(e).__name__}: {e}")
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

        await self._create_client()  # Ensure client session exists

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
                    final_url = str(response.url)  # Convert URL object to string
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
            self.logger.exception(f"An unexpected error occurred: {e}")  # Log the exception
            return None

    async def extract_cited_title(self, cited_by_url):
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
        if depth > max_depth:
            return []  # Return an empty list for consistency

        self.logger.info(f"Fetching cited-by page (depth {depth}): {url}")
        html_content = await self.fetch_page(url)  # Reuse existing fetch_page
        tasks = []
        if html_content:
            try:
                cited_by_results = self.parser.parse_results(html_content)
                for result in cited_by_results:
                    # Add to graph *before* recursive call
                    cited_title = await self.extract_cited_title(result.get("cited_by_url"))
                    graph_builder.add_citation(result["title"], url, result.get("cited_by_url"), cited_title)

                    if result.get("cited_by_url") and depth + 1 <= max_depth:  # Check max_depth here
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
    ):  # Add new parameters
        all_results = []
        start_index = 0
        query_builder = QueryBuilder()

        await self._create_client()  # Initialize the client session
        self.start_time = time.monotonic()  # Record start time

        # Use tqdm to wrap the outer loop
        with tqdm(total=num_results, desc="Scraping Results", unit="result") as pbar:
            while len(all_results) < num_results:
                # Pass the new parameters to build_url
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

                    # Fetch citation information concurrently
                    citation_tasks = []
                    for item, result in zip(raw_items, results):
                        pdf_url = None
                        if result.get("doi"):
                            pdf_url = await self.scrape_pdf_link(result["doi"])
                        if not pdf_url:
                            extracted_url = self.parser.extract_pdf_url(item)
                            if extracted_url:
                                pdf_url = (
                                    "https://scholar.google.com" + extracted_url
                                    if extracted_url.startswith("/")
                                    else extracted_url
                                )
                        if pdf_url:
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

                    # Flatten the list of lists and gather all citation tasks
                    nested_tasks = await asyncio.gather(*citation_tasks)
                    flat_tasks = [task for sublist in nested_tasks for task in sublist]
                    while flat_tasks:
                        next_level_tasks = await asyncio.gather(*flat_tasks)
                        flat_tasks = [task for sublist in next_level_tasks for task in sublist]

                    # Update pbar for each page.
                    pbar.update(len(results))

                    # Calculate and display statistics
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
        """Fetches and parses an author's profile page.

        Args:
            author_id: The Google Scholar ID of the author.

        Returns:
            A dictionary containing the author's profile information, or None
            if an error occurred.

        """
        url = QueryBuilder().build_author_profile_url(author_id)  # Use the new method
        html_content = await self.fetch_page(url)
        if html_content:
            try:
                author_data = self.author_parser.parse_profile(html_content)  # New parser method
                return author_data
            except ParsingException as e:
                self.logger.error(f"Error parsing author profile: {e}")
                return None
        return None

    def calculate_rps(self):
        """Calculates the rolling average of requests per second."""
        if len(self.request_times) < 2:
            return 0  # Not enough data
        total_time = self.request_times[-1] - self.request_times[0]
        if total_time == 0:
            return 0  # Avoid division by zero
        return (len(self.request_times) - 1) / total_time

    def calculate_etr(self, rps, total_results, results_collected):
        """Calculates the estimated time remaining."""
        if rps == 0:
            return None
        remaining_results = total_results - results_collected
        if remaining_results <= 0:
            return 0
        return remaining_results / rps
