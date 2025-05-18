# fetcher.py
import asyncio
import logging
import os
import random
import re
import time
from typing import Dict, List, Optional

import aiohttp
from parsel import Selector
from tqdm import tqdm
from yarl import URL  # Import URL for type hinting and usage

from google_scholar_scraper.exceptions import CaptchaException, NoProxiesAvailable, ParsingException
from google_scholar_scraper.models import ProxyErrorType
from google_scholar_scraper.parser import AuthorProfileParser, Parser  # Make sure AuthorProfileParser is still used if needed
from google_scholar_scraper.proxy_manager import ProxyManager
from google_scholar_scraper.query_builder import QueryBuilder
from google_scholar_scraper.utils import detect_captcha, get_random_user_agent


class Fetcher:
    def __init__(self, proxy_manager=None, min_delay=2, max_delay=5, max_retries=3, rolling_window_size=20):
        """
        Initializes the Fetcher.

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
        assert self.client is not None, "Client session must be initialized by _create_client"

        proxy = await self.proxy_manager.get_proxy()  # Get a proxy *once* per fetch_page call
        if proxy:
            proxy_url = f"http://{proxy}"
            self.proxies_used.add(proxy)
        else:
            proxy_url = None
            self.logger.info(f"Attempting direct connection for {url} (no proxy).")

        for attempt in range(retry_count):
            # --- DEBUG: Return mock HTML for search result pages to bypass CAPTCHA ---
            # if "scholar.google.com/scholar?" in url:  # This check should be specific enough
            #     self.logger.warning(f"DEBUG MODE: Returning mock HTML for search URL: {url}")
            #     sample_html_content = """<html><body>
            # <div id="gs_res_ccl_mid">
            #   <div class="gs_r gs_or gs_scl">
            #     <div class="gs_ri">
            #       <h3 class="gs_rt">
            #         <a href="http://example.com/paper1">Sample Paper Title 1 (Mock)</a>
            #       </h3>
            #       <div class="gs_a">
            #         Author One, Author Two - Journal Of Samples, 2023 - example.com
            #       </div>
            #       <div class="gs_rs">This is a sample snippet for paper 1. It discusses important things.</div>
            #       <div class="gs_fl">
            #         <a href="http://example.com/citedby1">Cited by 10</a>
            #         <a href="http://example.com/related1">Related articles</a>
            #         <a href="http://example.com/pdf1.pdf">[PDF] example.com</a>
            #       </div>
            #     </div>
            #   </div>
            #   <div class="gs_r gs_or gs_scl">
            #     <div class="gs_ri">
            #       <h3 class="gs_rt">
            #         <a href="http://example.com/paper2">Second Sample Paper (Mock)</a>
            #       </h3>
            #       <div class="gs_a">
            #         Author Three - Another Journal, 2024 - example.org
            #       </div>
            #       <div class="gs_rs">This is a snippet for paper 2. More research here.</div>
            #       <div class="gs_fl">
            #         <a href="http://example.com/citedby2">Cited by 5</a>
            #         <a href="http://example.com/related2">Related articles</a>
            #       </div>
            #     </div>
            #   </div>
            # </div>
            # <div id="gs_n">
            #     <center>
            #         <table class="gs_n_nav">
            #             <tr>
            #                 <td class="gs_n_p"><a href="/scholar?start=0&q=test"><b></b><span class="gs_ico gs_ico_nav_page_L"></span>Previous</a></td>
            #                 <td class="gs_n_c" width="54%"><a href="/scholar?start=0&q=test">1</a></td>
            #                 <td class="gs_n_c"><a href="/scholar?start=10&q=test">2</a></td>
            #                 <td class="gs_n_n"><a href="/scholar?start=10&q=test">Next<span class="gs_ico gs_ico_nav_page_R"></span></a></td>
            #             </tr>
            #         </table>
            #     </center>
            # </div>
            # </body></html>"""
            #     return sample_html_content
            # # --- END DEBUG ---
            try:
                delay = await self._get_delay()
                await asyncio.sleep(delay)
                request_start_time = time.monotonic()

                request_args = {"headers": headers, "timeout": aiohttp.ClientTimeout(total=10)}
                if proxy_url:
                    request_args["proxy"] = proxy_url
                    # Disable SSL verification when using a proxy to handle proxies
                    # that might be doing SSL interception with self-signed certs.
                    # This has security implications but may be necessary for some free proxies.
                    request_args["ssl"] = False
                # For direct connections (proxy_url is None), default SSL verification will apply.

                # Ensure self.client is used here
                async with self.client.get(url, **request_args) as response:
                    try:
                        response.raise_for_status()
                        html_content = await response.text()
                        if detect_captcha(html_content):
                            # Log a snippet of HTML that triggered CAPTCHA detection for review
                            self.logger.warning(f"CAPTCHA detected for {url}. HTML snippet: {html_content[:500]}...")
                            raise CaptchaException("CAPTCHA detected!")

                        self.successful_requests += 1
                        request_end_time = time.monotonic()
                        self.request_times.append(request_end_time - request_start_time)
                        self.request_times = self.request_times[-self.rolling_window_size :]
                        if proxy:
                            self.proxy_manager.mark_proxy_success(proxy)
                        return html_content
                    except aiohttp.ClientResponseError as http_err:
                        # Log response text for HTTP errors before re-raising
                        error_text_snippet = "Could not read response body on HTTP error."
                        try:
                            # Access text from the 'response' object, not 'http_err'
                            error_body = await response.text()
                            error_text_snippet = error_body[:500]
                        except Exception as text_read_err:
                            self.logger.warning(f"Could not read response text on HTTP error for {url}: {text_read_err}")
                        self.logger.warning(
                            f"HTTP error {http_err.status} for {url} with proxy {proxy}. "
                            f"Message: {http_err.message}. Response snippet: {error_text_snippet}..."
                        )
                        # Ensure the original http_err is raised to be caught by the broader except block below
                        # for consistent error handling (proxy marking, retries etc.)
                        raise http_err  # Re-raise the caught http_err specifically

            except (
                aiohttp.ClientError,
                asyncio.TimeoutError,
                CaptchaException,
            ) as e:  # This will now catch the re-raised http_err too
                self.failed_requests += 1
                # The warning for HTTP error is now logged above with more detail.
                # We can make this log more general or conditional if needed.
                if not isinstance(e, aiohttp.ClientResponseError):  # Avoid double logging for HTTP errors already detailed
                    self.logger.warning(f"Attempt {attempt + 1} failed for {url}: {type(e).__name__}: {e} with proxy {proxy}")

                if isinstance(e, CaptchaException):  # This check remains valid
                    if proxy:
                        self.proxy_manager.mark_proxy_failure(proxy, ProxyErrorType.CAPTCHA)
                        self.proxy_manager.remove_proxy(proxy)  # remove_proxy implies blacklisting
                    self.proxies_removed += 1  # This might be redundant if remove_proxy handles it conceptually
                    try:
                        await self.proxy_manager.refresh_proxies()
                    except NoProxiesAvailable:
                        self.logger.error("No proxies available after CAPTCHA and refresh attempt.")
                        # Do not return None yet, let retry loop continue if attempts left
                    # For CAPTCHA, we might want to break the retry loop for this proxy or URL immediately
                    # The current logic will retry with the same (now removed) proxy if retries > 1
                    # which is not ideal. For now, let it be, but it's a point of improvement.
                    # Returning None here means the fetch_page call fails for this URL.
                    return None  # Fail fast on CAPTCHA for this page fetch.

                # Handle other errors for retry logic
                error_type_to_mark = ProxyErrorType.OTHER
                if isinstance(e, asyncio.TimeoutError):
                    error_type_to_mark = ProxyErrorType.TIMEOUT
                elif isinstance(e, aiohttp.ClientProxyConnectionError):  # More specific connection error
                    error_type_to_mark = ProxyErrorType.CONNECTION

                if proxy:
                    self.proxy_manager.mark_proxy_failure(proxy, error_type_to_mark)

                if attempt == retry_count - 1:  # Last attempt failed
                    if proxy:
                        self.proxy_manager.remove_proxy(proxy)  # Remove after all retries failed
                        self.proxies_removed += 1
                    self.logger.error(f"Failed to fetch {url} after {retry_count} attempts with proxy {proxy}.")
                    return None  # Failed all retries for this URL
                else:
                    # Wait before retrying with the same proxy (if it wasn't removed due to CAPTCHA)
                    await asyncio.sleep(random.uniform(2, 5))

            except NoProxiesAvailable:  # This might be raised by refresh_proxies
                self.logger.error(
                    "NoProxiesAvailable encountered during fetch_page for %s. Cannot continue fetching this page.", url
                )
                return None  # Failed to fetch this page due to lack of proxies

        # If loop finishes without returning (e.g. retry_count was 0, though it's >=1)
        self.logger.error(f"fetch_page for {url} completed all retries without success or specific error return.")
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
        assert self.client is not None, "Client session must be initialized by _create_client"

        proxy = await self.proxy_manager.get_proxy()
        proxy_url = f"http://{proxy}" if proxy else None

        for attempt in range(retries):
            try:
                request_args = {"headers": headers, "timeout": aiohttp.ClientTimeout(total=20)}
                if proxy_url:
                    request_args["proxy"] = proxy_url

                async with self.client.get(url, **request_args) as response:
                    response.raise_for_status()
                    if response.headers.get("Content-Type") == "application/pdf":
                        with open(filename, "wb") as f:
                            async for chunk in response.content.iter_chunked(1024):
                                f.write(chunk)
                        self.logger.info(f"Downloaded PDF to {filename}")
                        self.pdfs_downloaded += 1
                        if proxy:
                            self.proxy_manager.mark_proxy_success(proxy)
                        return True
                    else:
                        self.logger.warning(
                            f"URL {url} did not return a PDF (Content-Type: {response.headers.get('Content-Type')})."
                        )
                        return False
            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                self.logger.warning(
                    f"Attempt {attempt + 1}/{retries} to download PDF {url} failed: {type(e).__name__}: {e} (Proxy: {proxy_url})"
                )
                error_type_to_mark = ProxyErrorType.OTHER
                if isinstance(e, asyncio.TimeoutError):
                    error_type_to_mark = ProxyErrorType.TIMEOUT
                elif isinstance(e, aiohttp.ClientProxyConnectionError):
                    error_type_to_mark = ProxyErrorType.CONNECTION

                if proxy:  # Mark failure for the current proxy
                    self.proxy_manager.mark_proxy_failure(proxy, error_type_to_mark)

                if attempt == retries - 1:
                    self.logger.error(f"All {retries} attempts to download PDF {url} failed.")
                    if proxy:  # Remove proxy after all retries with it failed
                        self.proxy_manager.remove_proxy(proxy)
                    return False  # Failed all retries

                # If not the last attempt, try to get a new proxy for the next attempt
                # (or continue with no proxy if that was the case)
                try:
                    # Potentially refresh or get a new proxy before next sleep/retry
                    # For simplicity, current logic retries with same proxy or no proxy.
                    # If proxy failed, it's marked. A more robust retry might get a *new* proxy here.
                    # For now, just log and sleep.
                    if proxy:  # If a proxy was used and failed, it's good to try to refresh the list
                        self.logger.info(
                            f"Proxy {proxy} failed for PDF download, attempting to refresh proxy list before next retry."
                        )
                        await self.proxy_manager.refresh_proxies()  # Attempt to get fresh proxies
                        # Get a new proxy for the next attempt
                        new_proxy = await self.proxy_manager.get_proxy()
                        if new_proxy != proxy:  # If we got a different proxy
                            self.logger.info(f"Retrying PDF download with new proxy: {new_proxy}")
                            proxy = new_proxy  # Update current proxy
                            proxy_url = f"http://{proxy}" if proxy else None
                        elif new_proxy == proxy and proxy is not None:
                            self.logger.warning(f"Got the same proxy {proxy} after refresh. Retrying with it.")
                        elif new_proxy is None and proxy is not None:
                            self.logger.warning(
                                "No new proxy available after refresh, attempting direct connection for next retry."
                            )
                            proxy = None
                            proxy_url = None
                        # If new_proxy is None and proxy was already None, continue direct.

                except NoProxiesAvailable:
                    self.logger.warning("No proxies available during PDF download retry for %s. Attempting direct.", url)
                    proxy = None  # Fallback to direct connection for next attempt
                    proxy_url = None

                await asyncio.sleep(random.uniform(5, 10))  # Shorter sleep for PDF retries

            except NoProxiesAvailable:  # Should ideally be caught by proxy_manager calls if it happens there
                self.logger.error("NoProxiesAvailable caught directly during PDF download for %s. Cannot continue.", url)
                return False

        self.logger.error(f"PDF download for {url} failed after all retry attempts (loop completed).")
        return False  # Fallback if loop completes (e.g., retries = 0, though current code sets retries=3)

    async def scrape_pdf_link(self, doi: str) -> Optional[str]:
        """Scrapes a PDF link from a DOI using Unpaywall and direct scraping."""
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
            "Referer": "https://scholar.google.com",
        }
        unpaywall_url = f"https://api.unpaywall.org/v2/{doi}?email=unpaywall@impactstory.org"

        await self._create_client()
        assert self.client is not None, "Client session must be initialized by _create_client"

        try:
            pdf_url = None  # Initialize pdf_url here
            # First, try Unpaywall
            async with self.client.get(unpaywall_url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                response.raise_for_status()
                data = await response.json()
                paper_url = data.get("doi_url")  # This is the publisher's page for the article

                if data.get("is_oa") and data.get("best_oa_location") and data["best_oa_location"].get("url_for_pdf"):
                    pdf_url = data["best_oa_location"]["url_for_pdf"]
                    self.logger.info(f"Found OA PDF URL via Unpaywall best_oa_location: {pdf_url} for DOI: {doi}")
                    return pdf_url

                # If Unpaywall didn't give a direct PDF, or if it's not OA, try scraping the paper_url
                if not paper_url:
                    self.logger.warning(f"Unpaywall did not provide a doi_url (publisher page) for DOI: {doi}")
                    return None  # Cannot proceed to scrape publisher page

                self.logger.info(f"Paper is_oa: {data.get('is_oa')}. Publisher page: {paper_url}. Attempting to scrape for PDF.")

            # Scrape the publisher page (paper_url from Unpaywall)
            async with self.client.get(paper_url, headers=headers, timeout=aiohttp.ClientTimeout(total=20)) as response:
                response.raise_for_status()
                self.logger.info(f"Final URL after redirect from publisher page: {response.url}")
                final_url_str = str(response.url)  # Use a consistent variable name
                html_content = await response.text()
                selector = Selector(text=html_content)

                # Try common meta tag
                meta_pdf_url = selector.xpath("//meta[@name='citation_pdf_url']/@content").get()
                if meta_pdf_url:
                    self.logger.info(f"Found PDF URL in meta tag: {meta_pdf_url}")
                    return meta_pdf_url

                # Site-specific scraping logic (ensure final_url_str is used)
                # (Keep existing site-specific logic, ensuring it uses final_url_str and response.url.join correctly)
                for link_tag in selector.xpath("//a[@href]"):  # Iterate over link tags
                    href = link_tag.xpath("@href").get()
                    if not href:
                        continue

                    # Nature
                    if "nature.com" in final_url_str:
                        if "/articles/" in href and href.endswith(".pdf"):  # Common pattern
                            return str(response.url.join(URL(href)))
                        if "/content/pdf/" in href and href.endswith(".pdf"):  # Another common pattern
                            return str(response.url.join(URL(href)))
                    # Add other site-specific patterns here if needed, e.g., ScienceDirect, IEEE
                    if "sciencedirect.com" in final_url_str:
                        pdf_url_attr = link_tag.xpath("@pdfurl").get()  # Check for specific attribute
                        if pdf_url_attr:
                            return str(response.url.join(URL(pdf_url_attr)))
                        if "pdf" in href.lower() and "download" in href.lower():  # General pattern
                            return str(response.url.join(URL(href)))
                    if "ieeexplore.ieee.org" in final_url_str:
                        # The regex for embedded JSON might be too specific, general link finding is better
                        if "/stamp/stamp.jsp" in href and "arnumber=" in href:  # Often leads to PDF
                            # This might require another hop or JavaScript, harder to get directly
                            self.logger.info(f"Found IEEE stamp link, might be PDF: {href}")
                        if href.endswith(".pdf") and "document" in href.lower():
                            return str(response.url.join(URL(href)))

                # Generic PDF link patterns (as a fallback)
                # Ensure this part is robust and doesn't pick wrong links
                PDF_PATTERNS = [".pdf", "/pdf/", "download", "fulltext"]  # Simplified and common
                links = selector.css("a::attr(href)").getall()

                # Prioritize links containing the DOI or parts of it, or common keywords
                # This part needs careful crafting to avoid false positives
                best_candidate = None
                for link_text in links:
                    link_lower = link_text.lower()
                    if any(pattern in link_lower for pattern in PDF_PATTERNS):
                        # Further heuristics could be added here, e.g., link text
                        # For now, take the first plausible one
                        candidate_url = str(response.url.join(URL(link_text)))
                        if ".pdf" in candidate_url.lower():  # Prefer direct .pdf links
                            self.logger.info(f"Found generic PDF pattern match: {candidate_url}")
                            return candidate_url
                        if not best_candidate:
                            best_candidate = candidate_url  # Store first plausible non-.pdf link

                if best_candidate:
                    self.logger.info(f"Found plausible generic link (non-direct .pdf): {best_candidate}")
                    return best_candidate

                self.logger.warning(
                    f"No PDF link found on publisher page {final_url_str} for DOI {doi} after trying all methods."
                )
                return None

        except aiohttp.ClientResponseError as e:
            self.logger.error(
                f"HTTP error scraping PDF link for DOI {doi} (URL: {e.request_info.url if e.request_info else 'N/A'}): {e.status} {e.message}"
            )
            return None
        except aiohttp.ClientError as e:  # Catch other client errors like connection issues
            self.logger.error(f"Client error scraping PDF link for DOI {doi}: {e}")
            return None
        except Exception as e:
            self.logger.exception(f"An unexpected error occurred scraping PDF link for DOI {doi}: {e}")
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
        download_pdfs: bool = False,
    ):
        """
        Scrapes Google Scholar search results and related information.

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
            download_pdfs (bool): Whether to attempt to download PDFs. Defaults to False.

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
                    pbar.set_description_str(f"Skipping cached URL: {url[:50]}...")  # Update description
                    continue

                html_content = await self.fetch_page(url)
                if not html_content:
                    self.logger.warning(f"No HTML content for {url}, skipping page.")
                    start_index += 10  # Ensure we move to next page even on fetch failure
                    # Potentially update pbar if we consider this a "processed" page attempt
                    # pbar.update(0) # Or some other way to indicate an attempt without results
                    continue

                try:
                    # Ensure parser methods are called correctly
                    parsed_results_list = self.parser.parse_results(html_content, True)
                    raw_items_list = self.parser.parse_raw_items(html_content)

                    # Ensure both lists have the same length before zipping
                    min_len = min(len(parsed_results_list), len(raw_items_list))
                    if len(parsed_results_list) != len(raw_items_list):
                        self.logger.warning(
                            f"Mismatch in parsed results ({len(parsed_results_list)}) and raw items ({len(raw_items_list)}) for URL {url}. Using min length {min_len}."
                        )

                    # Use the shorter length for zipping to avoid errors
                    parsed_results_with_items = list(zip(parsed_results_list[:min_len], raw_items_list[:min_len]))

                    # These are the results for the current page
                    results_on_page = [result_item[0] for result_item in parsed_results_with_items]
                    # raw_items_on_page = [result_item[1] for result_item in parsed_results_with_items] # If needed

                    if not results_on_page:
                        self.logger.info(f"No results parsed from page: {url}. Stopping for this query.")
                        break

                    citation_tasks = []
                    for result_data in results_on_page:  # Iterate over results_on_page
                        if download_pdfs:
                            pdf_downloaded_path = None
                            # Attempt 1: Use existing pdf_url from parser if available
                            if result_data.get("pdf_url"):
                                direct_pdf_url = result_data["pdf_url"]
                                safe_title = re.sub(r'[\\/*?:"<>|]', "", result_data.get("title", "untitled"))
                                year_str = str(result_data.get("year", "unknown"))
                                pdf_filename_direct = os.path.join(pdf_dir, f"{safe_title}_{year_str}_direct.pdf")
                                if await self.download_pdf(direct_pdf_url, pdf_filename_direct):
                                    pdf_downloaded_path = pdf_filename_direct
                                    self.logger.info(f"PDF downloaded (direct link) to: {pdf_downloaded_path}")

                            # Attempt 2: Try finding PDF via DOI if no direct link or direct download failed
                            if not pdf_downloaded_path and result_data.get("doi"):
                                self.logger.info(
                                    f"Attempting to find PDF via DOI: {result_data['doi']} for '{result_data.get('title', 'N/A')}'"
                                )
                                pdf_url_from_doi = await self.scrape_pdf_link(result_data["doi"])
                                if pdf_url_from_doi:
                                    result_data["pdf_url"] = pdf_url_from_doi  # Update with potentially better URL
                                    safe_title = re.sub(r'[\\/*?:"<>|]', "", result_data.get("title", "untitled"))
                                    year_str = str(result_data.get("year", "unknown"))
                                    pdf_filename_doi = os.path.join(pdf_dir, f"{safe_title}_{year_str}_doi.pdf")
                                    if await self.download_pdf(pdf_url_from_doi, pdf_filename_doi):
                                        pdf_downloaded_path = pdf_filename_doi
                                        self.logger.info(f"PDF downloaded (DOI link) to: {pdf_downloaded_path}")
                                else:
                                    self.logger.info(f"No PDF link found via DOI for: {result_data['doi']}")

                            if pdf_downloaded_path:
                                result_data["pdf_path"] = pdf_downloaded_path
                            else:
                                if result_data.get("pdf_url") or result_data.get("doi"):  # Only log if we tried
                                    self.logger.warning(f"Failed to download PDF for: {result_data.get('title', 'N/A')}")

                        # Add result to data_handler
                        db_id = await data_handler.add_result(result_data)
                        if db_id:  # If result was successfully added (e.g., not a duplicate if DH handles that)
                            # Add citation link to graph_builder
                            cited_title = await self.extract_cited_title(result_data.get("cited_by_url"))
                            graph_builder.add_citation(
                                result_data["title"],
                                result_data.get("article_url"),
                                result_data.get("cited_by_url"),
                                cited_title,
                                result_data.get("doi"),
                            )
                            if result_data.get("cited_by_url") and max_depth > 0:  # Check max_depth before appending task
                                citation_tasks.append(
                                    self.fetch_cited_by_page(
                                        result_data["cited_by_url"], self.proxy_manager, 1, max_depth, graph_builder
                                    )
                                )

                    if citation_tasks:
                        nested_tasks = await asyncio.gather(*citation_tasks)
                        # Flattening logic for fetch_cited_by_page if it returns lists of tasks
                        flat_tasks = [task for sublist in nested_tasks for task in sublist if isinstance(sublist, list)]
                        while flat_tasks:  # Process further levels if any
                            next_level_tasks_results = await asyncio.gather(*flat_tasks)
                            flat_tasks = [
                                task for sublist in next_level_tasks_results for task in sublist if isinstance(sublist, list)
                            ]

                    all_results.extend(results_on_page)
                    pbar.update(len(results_on_page))

                    # Update progress display
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

                except ParsingException as e:
                    self.logger.error(f"Error parsing page {url}: {e}", exc_info=True)
                    # Optionally, decide if a parsing error for one page should stop all scraping
                    # For now, we just move to the next page index

                if len(all_results) >= num_results:
                    break

                next_page_url_segment = self.parser.find_next_page(html_content)
                if next_page_url_segment:
                    # url = urllib.parse.urljoin(base_url, next_page_url_segment) # Requires base_url
                    # Assuming next_page_url_segment is relative or needs to be combined with original query logic
                    start_index += 10  # Simple increment, QueryBuilder will construct full URL
                else:
                    self.logger.info("No next page found.")
                    break  # No more pages for this query

                await asyncio.sleep(await self._get_delay())  # Polite delay

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
        """
        Scrapes details for a single publication URL (e.g., from author profile).

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
