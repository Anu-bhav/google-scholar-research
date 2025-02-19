# google_scholar_research_tool.py
import argparse
import asyncio
import json
import logging
import os
import random
import re
import sqlite3
import time
import urllib.parse
from enum import Enum, auto
from typing import Dict, List, Optional

import aiohttp
import aiosqlite
import networkx as nx
import pandas as pd
from fake_useragent import UserAgent
from fp.fp import FreeProxy
from parsel import Selector
from tqdm import tqdm


# query_builder.py
class QueryBuilder:
    def __init__(self, base_url="https://scholar.google.com/scholar"):
        self.base_url = base_url

    def build_url(
        self,
        query=None,
        start=0,
        authors=None,
        publication=None,
        year_low=None,
        year_high=None,
        phrase=None,
        exclude=None,
        title=None,
        author=None,
        source=None,
    ):
        params = {
            "start": start,
            "hl": "en",
        }

        # Build the main query string
        if query:
            query_parts = []
            if phrase:
                query_parts.append(f'"{phrase}"')  # Enclose phrase in quotes
            else:
                query_parts.append(query)

            if exclude:
                excluded_terms = " ".join([f"-{term}" for term in exclude.split(",")])
                query_parts.append(excluded_terms)

            if title:
                query_parts.append(f"title:{title}")
            if author:
                query_parts.append(f"author:{author}")
            if source:
                query_parts.append(f"source:{source}")

            params["q"] = " ".join(query_parts)

        if authors:
            params["as_sauthors"] = authors
        if publication:
            params["as_publication"] = publication
        if year_low:
            params["as_ylo"] = year_low
        if year_high:
            params["as_yhi"] = year_high
        return f"{self.base_url}?{urllib.parse.urlencode(params)}"

    def build_author_profile_url(self, author_id):
        """Builds the URL for an author's profile page."""
        return f"https://scholar.google.com/citations?user={author_id}&hl=en"


# proxy_manager.py
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


# parser.py
class Parser:
    def __init__(self):
        self.logger = logging.getLogger(__name__)

    def parse_results(self, html_content, include_raw_item=False):
        selector = Selector(text=html_content)
        results = []

        for item_selector in selector.css("div.gs_ri"):
            try:
                title = self.extract_title(item_selector)
                authors, affiliations = self.extract_authors(item_selector)
                publication_info = self.extract_publication_info(item_selector)
                snippet = self.extract_snippet(item_selector)
                cited_by_count, cited_by_url = self.extract_cited_by(item_selector)
                related_articles_url = self.extract_related_articles_url(item_selector)
                article_url = self.extract_article_url(item_selector)
                doi = self.extract_doi(item_selector)

                result = {
                    "title": title,
                    "authors": authors,
                    "affiliations": affiliations,
                    "publication_info": publication_info,
                    "snippet": snippet,
                    "cited_by_count": cited_by_count,
                    "cited_by_url": cited_by_url,
                    "related_articles_url": related_articles_url,
                    "article_url": article_url,
                    "doi": doi,
                    "pdf_url": None,  # Initialize
                    "pdf_path": None,  # Initialize
                }

                if include_raw_item:
                    results.append((result, item_selector))  # include raw item
                else:
                    results.append(result)

            except Exception as e:
                self.logger.error(f"Error parsing an item: {e}")
                raise ParsingException(f"Error during parsing: {e}") from e
        return results

    def parse_raw_items(self, html_content):
        selector = Selector(text=html_content)
        return selector.css("div.gs_ri")

    def extract_title(self, item_selector):
        title_tag = item_selector.css("h3.gs_rt")
        if title_tag:
            link_element = title_tag.css("a::text").get()
            return link_element if link_element else title_tag.xpath("./text()").get().strip()
        return None

    def extract_authors(self, item_selector):
        authors_tag = item_selector.css("div.gs_a")
        if authors_tag:
            author_text = authors_tag.xpath("./text()").get()
            if author_text:
                match = re.match(r"(.*?)\s+-", author_text)
                if match:
                    authors_part = match.group(1).strip()
                    authors = [a.strip() for a in authors_part.split(",") if a.strip()]
                    if "ΓÇª" in authors_part or "..." in authors_part:
                        authors.append("et al.")
                    affiliations = []
                    parts = [part.strip() for part in author_text.split("-") if part.strip()]
                    if len(parts) > 1:
                        affiliation_text = parts[0].strip()
                        aff_parts = [aff.strip() for aff in affiliation_text.split(",") if aff.strip()]
                        affiliations = aff_parts[len(authors) :]
                    return authors, affiliations
        return [], []

    def extract_publication_info(self, item_selector):
        pub_info_tag = item_selector.css("div.gs_a")
        if pub_info_tag:
            pub_info_text = pub_info_tag.xpath("./text()").get()
            if pub_info_text:
                match = re.search(r"-\s*(.*?)\s*-\s*(.*)", pub_info_text)
                if match:
                    publication = match.group(1).strip()
                    year_match = re.search(r"\b\d{4}\b", match.group(2))
                    year = int(year_match.group(0)) if year_match else None
                    return {"publication": publication, "year": year}
        return {}

    def extract_snippet(self, item_selector):
        snippet_tag = item_selector.css("div.gs_rs")
        return snippet_tag.xpath("./text()").get().strip() if snippet_tag.xpath("./text()").get() else None

    def extract_cited_by(self, item_selector):
        cited_by_tag = item_selector.css("a[href*=scholar\\?cites]")
        if cited_by_tag:
            cited_by_text = cited_by_tag.xpath("./text()").get()
            match = re.search(r"\d+", cited_by_text) if cited_by_text else None
            cited_by_count = int(match.group(0)) if match else 0
            cited_by_url = "https://scholar.google.com" + cited_by_tag.attrib["href"] if cited_by_tag else None
            return cited_by_count, cited_by_url
        return 0, None

    def extract_related_articles_url(self, item_selector):
        related_tag = item_selector.css("a[href*=scholar\\?q=related]")
        return "https://scholar.google.com" + related_tag.attrib["href"] if related_tag else None

    def extract_article_url(self, item_selector):
        link_tag = item_selector.css("h3.gs_rt a")
        return link_tag.attrib["href"] if link_tag else None

    def extract_doi(self, item_selector):
        links_div = item_selector.css("div.gs_or_ggsm")
        if links_div:
            for link in links_div.css("a"):
                href = link.attrib["href"]
                if href:
                    match = re.search(r"https?://doi\.org/(10\.[^/]+/[^/]+)", href)
                    if match:
                        return match.group(1)
        return None

    def find_next_page(self, html_content):
        selector = Selector(text=html_content)
        next_button = selector.css('a[aria-label="Next"]')
        return next_button.attrib["href"] if next_button else None

    def extract_pdf_url(self, item_selector):
        pdf_link = item_selector.css('a[href*=".pdf"]')
        if pdf_link:
            return pdf_link.attrib["href"]

        article_link_tag = item_selector.css("h3.gs_rt a")
        if article_link_tag:
            article_url = article_link_tag.attrib["href"]
            if "ieeexplore.ieee.org" in article_url:
                return self.extract_pdf_from_ieee(article_url)  # IEEE-specific
        return None

    def extract_pdf_from_ieee(self, article_url):
        print(f"Attempting to extract PDF from IEEE: {article_url} (Placeholder)")
        return None


class AuthorProfileParser:
    def __init__(self):
        self.logger = logging.getLogger(__name__)

    def parse_profile(self, html_content):
        """Parses the HTML content of an author's profile page.

        Args:
            html_content: The HTML content of the page.

        Returns:
            A dictionary containing the extracted author information:
            {
                "name": str,
                "affiliation": str,
                "interests": list[str],
                "coauthors": list[dict],  # { "name": str, "link": str }
                "citations_all": int,
                "citations_since_year": int,
                "hindex_all": int,
                "hindex_since_year": int,
                "i10index_all": int,
                "i10index_since_year": int,
                "publications": list[dict],  # { "title": str, "link": str, ... }
            }

        """
        selector = Selector(text=html_content)
        try:
            name = selector.css("#gsc_prf_in::text").get()
            affiliation = selector.css("#gsc_prf_i+ .gsc_prf_il::text").get()
            interests = [interest.css("a::text").get() for interest in selector.css("#gsc_prf_int a")]
            coauthors = []
            for coauthor in selector.css("#gsc_rsb_coo a"):
                coauthor_name = coauthor.css("::text").get()
                coauthor_link = "https://scholar.google.com" + coauthor.attrib["href"]
                coauthors.append({"name": coauthor_name, "link": coauthor_link})

            # Use a more robust method to extract citation stats, handling missing values
            def safe_int(text):
                try:
                    return int(text)
                except (TypeError, ValueError):
                    return 0

            citations_all = safe_int(selector.xpath('//*[@id="gsc_rsb_st"]/tbody/tr[1]/td[2]/text()').get())
            citations_since_year = safe_int(selector.xpath('//*[@id="gsc_rsb_st"]/tbody/tr[1]/td[3]/text()').get())
            hindex_all = safe_int(selector.xpath('//*[@id="gsc_rsb_st"]/tbody/tr[2]/td[2]/text()').get())
            hindex_since_year = safe_int(selector.xpath('//*[@id="gsc_rsb_st"]/tbody/tr[2]/td[3]/text()').get())
            i10index_all = safe_int(selector.xpath('//*[@id="gsc_rsb_st"]/tbody/tr[3]/td[2]/text()').get())
            i10index_since_year = safe_int(selector.xpath('//*[@id="gsc_rsb_st"]/tbody/tr[3]/td[3]/text()').get())

            publications = []
            for pub in selector.css(".gsc_a_tr"):
                title = pub.css(".gsc_a_at::text").get()
                link = "https://scholar.google.com" + pub.css(".gsc_a_at::attr(href)").get()
                pub_info = pub.css(".gs_gray::text").getall()
                authors = pub_info[0] if len(pub_info) > 0 else ""
                publication_info = pub_info[1] if len(pub_info) > 1 else ""
                publications.append({"title": title, "link": link, "authors": authors, "publication_info": publication_info})

            return {
                "name": name,
                "affiliation": affiliation,
                "interests": interests,
                "coauthors": coauthors,
                "citations_all": citations_all,
                "citations_since_year": citations_since_year,
                "hindex_all": hindex_all,
                "hindex_since_year": hindex_since_year,
                "i10index_all": i10index_all,
                "i10index_since_year": i10index_since_year,
                "publications": publications,
            }

        except Exception as e:
            self.logger.error(f"Error parsing author profile: {e}")
            raise ParsingException(f"Error parsing author profile: {e}") from e


# fetcher.py
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


# data_handler.py
class DataHandler:
    def __init__(self, db_name="scholar_data.db"):
        self.db_name = db_name
        self.logger = logging.getLogger(__name__)

    async def create_table(self):
        async with aiosqlite.connect(self.db_name) as db:
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS results (
                    title TEXT, authors TEXT, publication_info TEXT, snippet TEXT,
                    cited_by_count INTEGER, related_articles_url TEXT,
                    article_url TEXT UNIQUE, pdf_url TEXT, pdf_path TEXT,
                    doi TEXT, affiliations TEXT, cited_by_url TEXT
                )
            """
            )
            await db.commit()

    async def insert_result(self, result):
        async with aiosqlite.connect(self.db_name) as db:
            try:
                await db.execute(
                    """
                    INSERT INTO results (title, authors, publication_info, snippet, cited_by_count,
                    related_articles_url, article_url, pdf_url, pdf_path, doi, affiliations, cited_by_url)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                    (
                        result["title"],
                        ",".join(result["authors"]),
                        json.dumps(result["publication_info"]),
                        result["snippet"],
                        result["cited_by_count"],
                        result["related_articles_url"],
                        result["article_url"],
                        result.get("pdf_url"),
                        result.get("pdf_path"),
                        result.get("doi"),
                        ",".join(result.get("affiliations", [])),
                        result.get("cited_by_url"),
                    ),
                )
                await db.commit()
            except sqlite3.IntegrityError:
                # self.logger.debug(f"Duplicate entry skipped: {result['article_url']}")
                pass  # Silently handle duplicates.

    async def result_exists(self, article_url):
        async with aiosqlite.connect(self.db_name) as db:
            async with db.execute("SELECT 1 FROM results WHERE article_url = ?", (article_url,)) as cursor:
                return await cursor.fetchone() is not None

    def save_to_csv(self, results: List[Dict], filename: str):
        if not results:
            self.logger.warning("No results to save.")
            return
        try:
            df = pd.DataFrame(results)
            df.to_csv(filename, index=False, encoding="utf-8")
        except Exception as e:
            self.logger.error("Error writing the csv", exc_info=True)

    def save_to_json(self, results, filename):
        with open(filename, "w", encoding="utf-8") as jsonfile:
            json.dump(results, jsonfile, indent=4)

    def save_to_dataframe(self, results):
        return pd.DataFrame(results)


# graph_builder.py
class GraphBuilder:
    def __init__(self):
        self.graph = nx.DiGraph()

    def add_citation(self, citing_title, citing_url, cited_by_url, cited_title=None):
        citing_node_id = citing_url or citing_title
        self.graph.add_node(citing_node_id, title=citing_title)
        cited_node_id = cited_by_url or "Unknown URL"
        cited_title = cited_title or cited_by_url or "Unknown Title"
        self.graph.add_node(cited_node_id, title=cited_title)
        if citing_node_id != cited_node_id:
            self.graph.add_edge(citing_node_id, cited_node_id)

    def save_graph(self, filename="citation_graph.graphml"):
        nx.write_graphml(self.graph, filename)

    def load_graph(self, filename="citation_graph.graphml"):
        try:
            self.graph = nx.read_graphml(filename)
        except FileNotFoundError:
            print(f"Graph file not found: {filename}")


# utils.py
def get_random_delay(min_delay=2, max_delay=5):
    return random.uniform(min_delay, max_delay)


def get_random_user_agent():
    ua = UserAgent()
    return ua.random


def detect_captcha(html_content: str) -> bool:
    """Detects CAPTCHA in HTML content."""
    # More robust CAPTCHA detection, including common phrases and patterns.
    captcha_patterns = [
        r"prove\s+you'?re\s+human",
        r"verify\s+you'?re\s+not\s+a\s+robot",
        r"complete\s+the\s+CAPTCHA",
        r"security\s+check",
        r"/sorry/image",  # Google's reCAPTCHA image URL
        r"recaptcha",  # Common reCAPTCHA keyword
        r"hcaptcha",  # hCaptcha keyword
        r"<img\s+[^>]*src=['\"]data:image/png;base64,",  # inline captcha image
        r"<iframe\s+[^>]*src=['\"]https://www\.google\.com/recaptcha/api[2]?/",  # reCAPTCHA iframe
    ]
    for pattern in captcha_patterns:
        if re.search(pattern, html_content, re.IGNORECASE):
            return True
    return False


# exceptions.py
class CaptchaException(Exception):
    """Raised when a CAPTCHA is detected."""

    pass


class ParsingException(Exception):
    """Raised when an error occurs during parsing."""

    pass


class NoProxiesAvailable(Exception):
    """Raised when no working proxies are found."""

    pass


# models.py
class ProxyErrorType(Enum):
    CONNECTION = auto()
    TIMEOUT = auto()
    FORBIDDEN = auto()
    OTHER = auto()
    CAPTCHA = auto()  # Specifically handle CAPTCHA


async def main():
    parser = argparse.ArgumentParser(description="Scrape Google Scholar search results.")
    parser.add_argument("query", help="The search query.", nargs="?")  # Make query optional
    parser.add_argument("-a", "--authors", help="Search by author(s).", default=None)
    parser.add_argument("-p", "--publication", help="Search by publication.", default=None)
    parser.add_argument("-l", "--year_low", type=int, help="Lower bound of year range.", default=None)
    parser.add_argument("-u", "--year_high", type=int, help="Upper bound of year range.", default=None)
    parser.add_argument("-n", "--num_results", type=int, default=10, help="Max number of results.")
    parser.add_argument("-o", "--output", default="results.csv", help="Output file (CSV or JSON).")
    parser.add_argument("--json", action="store_true", help="Output in JSON format.")
    parser.add_argument("--pdf_dir", default="pdfs", help="Directory for PDFs.")
    parser.add_argument("--max_depth", type=int, default=3, help="Max citation depth.")
    parser.add_argument("--graph_file", default="citation_graph.graphml", help="Citation graph filename.")

    # --- Advanced Search Options ---
    parser.add_argument("--phrase", help="Search for an exact phrase.", default=None)
    parser.add_argument("--exclude", help="Exclude keywords (comma-separated).", default=None)
    parser.add_argument("--title", help="Search within the title.", default=None)
    parser.add_argument("--author", help="Search within the author field.", default=None)
    parser.add_argument("--source", help="Search within the source (publication).", default=None)
    parser.add_argument("--min_citations", type=int, help="Minimum number of citations.", default=None)
    parser.add_argument("--author_profile", type=str, help="Scrape an author's profile by their ID.")  # Added author profile
    parser.add_argument(
        "--recursive", action="store_true", help="Recursively scrape author's publications."
    )  # Added recursive flag

    args = parser.parse_args()

    if not args.query and not args.author_profile:
        parser.error("Either a query or --author_profile must be provided.")

    proxy_manager = ProxyManager()
    fetcher = Fetcher(proxy_manager=proxy_manager)
    data_handler = DataHandler()
    graph_builder = GraphBuilder()

    await data_handler.create_table()
    os.makedirs(args.pdf_dir, exist_ok=True)

    try:
        await proxy_manager.get_working_proxies()
    except NoProxiesAvailable:
        logging.error("No working proxies. Exiting.")
        return

    if args.author_profile:
        author_data = await fetcher.fetch_author_profile(args.author_profile)
        if author_data:
            if args.json:
                data_handler.save_to_json(author_data, args.output)
            else:  # Save author to csv if not json.
                df = pd.DataFrame([author_data])
                df.to_csv(args.output, index=False)
            print(f"Author profile data saved to {args.output}")

            if args.recursive:
                pass  # TODO: implement fetch details and recursive scraping.
                # for publication in author_data['publications']:
                # result = await fetcher.fetch_page(publication["link"]) # Implement fetch page details.

        else:
            print(f"Failed to fetch author profile for ID: {args.author_profile}")

    else:
        results = await fetcher.scrape(
            args.query,
            args.authors,
            args.publication,
            args.year_low,
            args.year_high,
            args.num_results,
            args.pdf_dir,
            args.max_depth,
            graph_builder,
            data_handler,
            # Pass new arguments
            phrase=args.phrase,
            exclude=args.exclude,
            title=args.title,
            author=args.author,
            source=args.source,
        )

        # --- Data Filtering (Add this section) ---
        if args.min_citations:
            results = [result for result in results if result["cited_by_count"] >= args.min_citations]

        if args.json:
            data_handler.save_to_json(results, args.output)
        else:
            data_handler.save_to_csv(results, args.output)
        logging.info(f"Successfully scraped and saved {len(results)} results in {args.output}")

        print(f"Citation graph: {graph_builder.graph.number_of_nodes()} nodes, {graph_builder.graph.number_of_edges()} edges")
        graph_builder.save_graph(args.graph_file)
        print(f"Citation graph saved to {args.graph_file}")
    await fetcher.close()


if __name__ == "__main__":
    logging.basicConfig(
        format="%(asctime)s | %(levelname)s | %(filename)s:%(lineno)d | %(funcName)s | %(message)s",
        level=logging.DEBUG,
    )
    asyncio.run(main())
