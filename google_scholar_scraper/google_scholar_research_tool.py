import argparse
import asyncio
import json
import logging
import os
import random
import re
import sqlite3
import time
import urllib
import urllib.parse
from enum import Enum, auto
from typing import Dict, List, Optional

import aiohttp
import aiosqlite
import matplotlib.pyplot as plt
import networkx as nx
import pandas as pd
from fake_useragent import UserAgent
from fp.fp import FreeProxy
from parsel import Selector
from tqdm import tqdm

# cat google_scholar_scraper/exceptions.py google_scholar_scraper/models.py google_scholar_scraper/utils.py \
# google_scholar_scraper/query_builder.py google_scholar_scraper/proxy_manager.py google_scholar_scraper/parser.py \
# google_scholar_scraper/fetcher.py google_scholar_scraper/data_handler.py \
# google_scholar_scraper/graph_builder.py > google_scholar_research_tool.py


# exceptions.py
class CaptchaException(Exception):
    """Raised when a CAPTCHA is detected on a webpage.

    Indicates that the scraper has encountered a CAPTCHA challenge,
    likely due to excessive requests or bot-like behavior.  Handling this
    exception typically involves rotating proxies, reducing request frequency,
    or implementing CAPTCHA solving mechanisms.
    """

    pass


class ParsingException(Exception):
    """Raised when an error occurs during HTML parsing.

    Indicates that the scraper was unable to extract data from the HTML content
    as expected. This could be due to changes in the website's structure,
    unexpected content format, or issues with the parsing logic itself.
    """

    pass


class NoProxiesAvailable(Exception):
    """Raised when no working proxies are available.

    Indicates that the ProxyManager could not find any proxies that are
    currently working and not blacklisted.  This usually means proxy sources
    are exhausted, all proxies have failed, or there are network connectivity issues
    preventing proxy retrieval or testing.
    """

    pass


# models.py
class ProxyErrorType(Enum):
    CONNECTION = auto()
    TIMEOUT = auto()
    FORBIDDEN = auto()
    OTHER = auto()
    CAPTCHA = auto()  # Specifically handle CAPTCHA


# utils.py
def get_random_delay(min_delay=2, max_delay=5):
    """Generates a random delay between min_delay and max_delay seconds.

    This function is used to introduce delays between requests to avoid
    overloading servers and to mimic human-like browsing behavior, which can help
    prevent rate limiting or blocking.

    Args:
        min_delay (int, optional): Minimum delay in seconds. Defaults to 2.
        max_delay (int, optional): Maximum delay in seconds. Defaults to 5.

    Returns:
        float: A random delay value (in seconds) between min_delay and max_delay.

    """
    return random.uniform(min_delay, max_delay)


def get_random_user_agent():
    """Returns a random user agent string using the fake-useragent library.

    This function fetches a random user agent string, simulating different web browsers
    and operating systems.  Using a variety of user agents helps to avoid
    detection as a bot and reduces the chance of being blocked by websites.

    Returns:
        str: A random user agent string.

    """
    ua = UserAgent()
    return ua.random


def detect_captcha(html_content: str) -> bool:
    """Detects CAPTCHA indicators in HTML content using regular expressions.

    This function searches for common patterns and phrases within the HTML content
    that are indicative of a CAPTCHA challenge page. CAPTCHA detection is crucial
    for web scraping to identify when anti-bot measures are triggered.

    Args:
        html_content (str): The HTML content (as a string) to analyze for CAPTCHA indicators.

    Returns:
        bool: True if CAPTCHA is detected in the HTML content, False otherwise.

    """
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


class QueryBuilder:
    """Builds URLs for Google Scholar searches and author profiles.

    Attributes:
        base_url (str): The base URL for Google Scholar search.

    """

    def __init__(self, base_url="https://scholar.google.com/scholar"):
        """Initializes the QueryBuilder with a base URL.

        Args:
            base_url (str, optional): The base URL for Google Scholar.
                                       Defaults to "https://scholar.google.com/scholar".

        """
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
        """Builds a Google Scholar search URL based on provided parameters.

        Args:
            query (str, optional): The main search query. Defaults to None.
            start (int, optional): The starting result index. Defaults to 0.
            authors (str, optional): Search for specific authors. Defaults to None.
            publication (str, optional): Search within a specific publication. Defaults to None.
            year_low (int, optional): Lower bound of the publication year range. Defaults to None.
            year_high (int, optional): Upper bound of the publication year range. Defaults to None.
            phrase (str, optional): Search for an exact phrase. Defaults to None.
            exclude (str, optional): Keywords to exclude (comma-separated). Defaults to None.
            title (str, optional): Search within the title. Defaults to None.
            author (str, optional): Search within the author field. Defaults to None.
            source (str, optional): Search within the source (publication). Defaults to None.

        Returns:
            str: The constructed Google Scholar search URL.

        Raises:
            ValueError: If start is negative, or if year_low or year_high are invalid years.

        """
        if start < 0:
            raise ValueError("Start index cannot be negative.")
        if year_low is not None and not isinstance(year_low, int):  # More robust year validation could be added
            raise ValueError("year_low must be an integer year.")
        if year_high is not None and not isinstance(year_high, int):
            raise ValueError("year_high must be an integer year.")

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
        """Builds the URL for an author's profile page.

        Args:
            author_id (str): The Google Scholar ID of the author.

        Returns:
            str: The constructed author profile URL.

        """
        return f"https://scholar.google.com/citations?user={author_id}&hl=en"


class ProxyManager:
    def __init__(
        self, timeout=5, refresh_interval=300, blacklist_duration=600, num_proxies=50, blacklist_file="proxy_blacklist.json"
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
                direct_pdf_url = self.extract_direct_pdf_url(item_selector)

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
                    "pdf_url": direct_pdf_url,  # Initialize
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
        try:
            title_tag = item_selector.css("h3.gs_rt")
            if title_tag:
                link_element = title_tag.css("a::text").get()
                return link_element if link_element else title_tag.xpath("./text()").get().strip()
            return None
        except Exception as e:
            self.logger.error(f"Error extracting title: {e}")
            return None

    def extract_authors(self, item_selector):
        try:
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
                            affiliation_text = parts[1].strip()  # Corrected index to 1 to get affiliation part
                            aff_parts = [aff.strip() for aff in affiliation_text.split(",") if aff.strip()]
                            affiliations = aff_parts  # Affiliations are all parts after authors
                        return authors, affiliations
                return [], []  # Return empty lists if author_text parsing fails
            return [], []  # Return empty lists if authors_tag is not found
        except Exception as e:
            self.logger.error(f"Error extracting authors and affiliations: {e}")
            return [], []  # Return empty lists on exception

    def extract_publication_info(self, item_selector):
        try:
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
        except Exception as e:
            self.logger.error(f"Error extracting publication info: {e}")
            return {}

    def extract_snippet(self, item_selector):
        try:
            snippet_tag = item_selector.css("div.gs_rs")
            return snippet_tag.xpath("./text()").get().strip() if snippet_tag.xpath("./text()").get() else None
        except Exception as e:
            self.logger.error(f"Error extracting snippet: {e}")
            return None

    def extract_cited_by(self, item_selector):
        try:
            cited_by_tag = item_selector.css("a[href*=scholar\\?cites]")
            if cited_by_tag:
                cited_by_text = cited_by_tag.xpath("./text()").get()
                match = re.search(r"\d+", cited_by_text) if cited_by_text else None
                cited_by_count = int(match.group(0)) if match else 0
                cited_by_url = "https://scholar.google.com" + cited_by_tag.attrib["href"] if cited_by_tag else None
                return cited_by_count, cited_by_url
            return 0, None
        except Exception as e:
            self.logger.error(f"Error extracting cited_by info: {e}")
            return 0, None

    def extract_related_articles_url(self, item_selector):
        try:
            related_tag = item_selector.css("a[href*=scholar\\?q=related]")
            return "https://scholar.google.com" + related_tag.attrib["href"] if related_tag else None
        except Exception as e:
            self.logger.error(f"Error extracting related articles URL: {e}")
            return None

    def extract_article_url(self, item_selector):
        try:
            link_tag = item_selector.css("h3.gs_rt a")
            return link_tag.attrib["href"] if link_tag else None
        except Exception as e:
            self.logger.error(f"Error extracting article URL: {e}")
            return None

    def extract_doi(self, item_selector):
        try:
            links_div = item_selector.css("div.gs_or_ggsm")
            if links_div:
                for link in links_div.css("a"):
                    href = link.attrib["href"]
                    if href:
                        match = re.search(r"https?://doi\.org/(10\.[^/]+/[^/]+)", href)
                        if match:
                            return match.group(1)
            return None
        except Exception as e:
            self.logger.error(f"Error extracting DOI: {e}")
            return None

    def extract_direct_pdf_url(self, item_selector):
        """Extracts direct PDF link from the item, if present."""
        try:
            pdf_link_tag = item_selector.css("div.gs_ggsd a[href*='.pdf']")  # Look for links in gs_ggsd div with .pdf in href
            if pdf_link_tag:
                href = pdf_link_tag.attrib["href"]
                if not href.startswith(("http://", "https://")):  # Handle relative URLs
                    base_url = "https://scholar.google.com"  # Google Scholar base URL
                    href = urllib.parse.urljoin(base_url, href)
                return href
            return None
        except Exception as e:
            self.logger.error(f"Error extracting direct PDF URL: {e}")
            return None

    def find_next_page(self, html_content):
        selector = Selector(text=html_content)
        next_button = selector.css('a[aria-label="Next"]')
        return next_button.attrib["href"] if next_button else None


class AuthorProfileParser:
    # ... (rest of AuthorProfileParser class - no changes needed for now)
    def __init__(self):
        self.logger = logging.getLogger(__name__)

    def parse_profile(self, html_content):
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
        """Initializes the Fetcher."""
        self.proxy_manager = proxy_manager or ProxyManager()
        self.logger = logging.getLogger(__name__)
        self.client: Optional[aiohttp.ClientSession] = None
        self.min_delay = min_delay
        self.max_delay = max_delay
        self.max_retries = max_retries
        self.parser = Parser()
        self.author_parser = AuthorProfileParser()
        self.successful_requests = 0
        self.failed_requests = 0
        self.proxies_used = set()
        self.proxies_removed = 0
        self.pdfs_downloaded = 0
        self.request_times = []
        self.rolling_window_size = rolling_window_size
        self.start_time = None

    async def _create_client(self) -> aiohttp.ClientSession:
        if self.client is None or self.client.closed:
            timeout = aiohttp.ClientTimeout(total=10)
            self.client = aiohttp.ClientSession(timeout=timeout)
        return self.client

    async def _get_delay(self) -> float:
        return random.uniform(self.min_delay, self.max_delay)

    async def fetch_page(self, url: str, retry_count: Optional[int] = None) -> Optional[str]:
        headers = {"User-Agent": get_random_user_agent()}
        retry_count = retry_count or self.max_retries
        await self._create_client()
        proxy = await self.proxy_manager.get_random_proxy()
        if not proxy:
            self.logger.error("No proxies available at start of fetch for URL: %s", url)
            return None
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
                    self.proxy_manager.mark_proxy_success(proxy)
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
                    return None
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
                    await asyncio.sleep(random.uniform(2, 5))
            except NoProxiesAvailable:
                self.logger.error("No proxies available during fetching of %s", url)
                return None

    async def fetch_pages(self, urls: List[str]) -> List[Optional[str]]:
        await self._create_client()
        return await asyncio.gather(*[self.fetch_page(url) for url in urls])

    async def download_pdf(self, url: str, filename: str) -> bool:
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
                        self.proxy_manager.mark_proxy_success(proxy)
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

    async def scrape_pdf_link(self, doi: Optional[str] = None, paper_url: Optional[str] = None) -> Optional[str]:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
            "Referer": "https://scholar.google.com",
        }
        unpaywall_url = None

        await self._create_client()
        pdf_url = None

        if doi:
            unpaywall_url = f"https://api.unpaywall.org/v2/{doi}?email=unpaywall@impactstory.org"

        try:
            if unpaywall_url:
                async with self.client.get(unpaywall_url, timeout=10) as response:
                    response.raise_for_status()
                    data = await response.json()
                    paper_url_unpaywall = data.get("doi_url")
                    if data.get("is_oa"):
                        self.logger.info(f"Paper is Open Access according to Unpaywall. DOI: {doi}")
                    else:
                        self.logger.info(f"Paper is NOT Open Access according to Unpaywall. DOI: {doi}")
                    paper_url_to_scrape = paper_url_unpaywall
            elif paper_url:
                paper_url_to_scrape = paper_url
            else:
                return None

            if paper_url_to_scrape:
                async with self.client.get(paper_url_to_scrape, headers=headers, timeout=20, allow_redirects=True) as response:
                    response.raise_for_status()
                    self.logger.info(f"Final URL after redirect: {response.url}")
                    final_url = str(response.url)
                    selector = Selector(text=await response.text())
                    meta_pdf_url = selector.xpath("//meta[@name='citation_pdf_url']/@content").get()
                    if meta_pdf_url:
                        self.logger.info(f"Found PDF URL in meta tag: {meta_pdf_url}")
                        return meta_pdf_url

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

                    doi_last_3 = doi[-3:] if doi and len(doi) >= 3 else ""
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
                            if doi_last_3 and doi_last_3 in link.lower():
                                pdf_url = str(response.url.join(link))
                                return str(pdf_url)
                            pdf_url = str(response.url.join(link))
                            return str(pdf_url)

                    return None

        except aiohttp.ClientResponseError as e:
            if e.status == 404 and unpaywall_url:
                self.logger.error(f"Paper with DOI {doi} not found by Unpaywall")
            return None
        except aiohttp.ClientError:
            return None
        except Exception as e:
            self.logger.exception(f"An unexpected error occurred: {e}")
            return None
        return pdf_url

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
        if self.client and not self.client.closed:
            await self.client.close()

    def calculate_rps(self):
        if len(self.request_times) < 2:
            return 0
        total_time = self.request_times[-1] - self.request_times[0]
        if total_time == 0:
            return 0
        return (len(self.request_times) - 1) / total_time

    def calculate_etr(self, rps, total_results, results_collected):
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
                    for result_item in parsed_results_with_items:
                        result, raw_item = result_item
                        pdf_url = result.get("pdf_url")  # Direct PDF URL from Parser (if any)

                        if not pdf_url:  # If no direct PDF URL, try scraping from article page
                            pdf_url_article_page = await self.scrape_pdf_link(
                                paper_url=result.get("article_url"), doi=result.get("doi")
                            )  # Pass article_url and doi
                            if pdf_url_article_page:
                                pdf_url = pdf_url_article_page  # Use article page PDF if found

                        if pdf_url:  # If ANY pdf_url found
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
                    logging.debug(f"Current all_results length: {len(all_results)}, target num_results: {num_results}")
                    # next_page = self.parser.find_next_page(html_content)
                    # if next_page:
                    #     start_index += 10
                    # else:
                    #     break
                    start_index += 10

                except ParsingException:
                    start_index += 10
                    continue

        return all_results[:num_results]

    async def fetch_author_profile(self, author_id: str):
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
        html_content = await self.fetch_page(publication_url)
        if html_content:
            try:
                publication_details = self.parser.parse_results(html_content)
                return publication_details
            except ParsingException as e:
                self.logger.error(f"Error parsing publication details from {publication_url}: {e}")
                return None
        return None


# data_handler.py
class DataHandler:
    """Handles data storage and retrieval operations for scraped Google Scholar results.

    Supports saving data to an SQLite database, CSV files, and JSON files.
    """

    def __init__(self, db_name="scholar_data.db"):
        """Initializes the DataHandler with a database name.

        Args:
            db_name (str, optional): The name of the SQLite database file.
                                     Defaults to "scholar_data.db".

        """
        self.db_name = db_name
        self.logger = logging.getLogger(__name__)

    async def create_table(self):
        """Creates the 'results' table in the SQLite database if it doesn't exist.

        The table schema includes fields for title, authors, publication info, snippet,
        citation counts, URLs, PDF information, DOI, and affiliations.
        """
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
            self.logger.info(f"Table 'results' created or already exists in database '{self.db_name}'")

    async def insert_result(self, result: Dict):
        """Inserts a single scraped result into the 'results' table.

        Handles SQLiteIntegrityError for duplicate entries (based on article_url)
        by logging a debug message and skipping the insertion. Logs other database
        errors to the error level.

        Args:
            result (Dict): A dictionary containing the scraped result data.
                           Expected keys: title, authors, publication_info, snippet,
                           cited_by_count, related_articles_url, article_url, pdf_url,
                           pdf_path, doi, affiliations, cited_by_url.

        """
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
                self.logger.debug(f"Inserted result: {result['article_url']}")
            except sqlite3.IntegrityError:
                self.logger.debug(f"Duplicate entry skipped: {result['article_url']}")
                pass  # Silently handle duplicates.
            except Exception as e:
                self.logger.error(f"Database error during insertion: {e}", exc_info=True)
                pass  # Log and skip on other database errors

    async def result_exists(self, article_url: str) -> bool:
        """Checks if a result with the given article_url already exists in the database.

        Args:
            article_url (str): The article URL to check for existence.

        Returns:
            bool: True if a result with the given URL exists, False otherwise.

        """
        async with aiosqlite.connect(self.db_name) as db:
            async with db.execute("SELECT 1 FROM results WHERE article_url = ?", (article_url,)) as cursor:
                exists = await cursor.fetchone() is not None
                self.logger.debug(f"Checked result existence for '{article_url}': {'Exists' if exists else 'Not Exists'}")
                return exists

    def save_to_csv(self, results: List[Dict], filename: str):
        """Saves a list of scraped results to a CSV file.

        Uses pandas DataFrame for efficient CSV writing.

        Args:
            results (List[Dict]): A list of dictionaries, where each dictionary
                                 represents a scraped result.
            filename (str): The name of the CSV file to save to.

        """
        if not results:
            self.logger.warning("No results to save to CSV.")
            return
        try:
            df = pd.DataFrame(results)
            df.to_csv(filename, index=False, encoding="utf-8")
            self.logger.info(f"Successfully saved {len(results)} results to CSV file: {filename}")
        except Exception as e:
            self.logger.error(f"Error writing to CSV file '{filename}': {e}", exc_info=True)

    def save_to_json(self, results: List[Dict], filename: str):
        """Saves a list of scraped results to a JSON file.

        Args:
            results (List[Dict]): A list of dictionaries, where each dictionary
                                 represents a scraped result.
            filename (str): The name of the JSON file to save to.

        """
        if not results:
            self.logger.warning("No results to save to JSON.")
            return
        try:
            with open(filename, "w", encoding="utf-8") as jsonfile:
                json.dump(results, jsonfile, indent=4, ensure_ascii=False)  # ensure_ascii=False for Unicode
            self.logger.info(f"Successfully saved {len(results)} results to JSON file: {filename}")
        except Exception as e:
            self.logger.error(f"Error writing to JSON file '{filename}': {e}", exc_info=True)

    def save_to_dataframe(self, results: List[Dict]) -> pd.DataFrame:
        """Converts a list of scraped results to a pandas DataFrame.

        Args:
            results (List[Dict]): A list of dictionaries, where each dictionary
                                 represents a scraped result.

        Returns:
            pd.DataFrame: A pandas DataFrame containing the scraped results.
                          Returns an empty DataFrame if input results are empty.

        """
        if not results:
            self.logger.warning("No results to convert to DataFrame. Returning empty DataFrame.")
            return pd.DataFrame()  # Return empty DataFrame if no results
        try:
            return pd.DataFrame(results)
        except Exception as e:
            self.logger.error(f"Error converting results to DataFrame: {e}", exc_info=True)
            return pd.DataFrame()  # Return empty DataFrame on error


# graph_builder.py
class GraphBuilder:
    """Builds and manages a citation graph using networkx.

    Nodes in the graph represent academic papers, and edges represent citations
    between them.  Graph is persisted to and loaded from GraphML files.

    Supports graph visualization with customizable layouts and centrality-based filtering.
    Generates visualizations in 'graph_citations' folder by default, with spring, circular, and kamada_kawai layouts.
    """

    def __init__(self):
        """Initializes the GraphBuilder with an empty directed graph."""
        self.graph = nx.DiGraph()
        self.logger = logging.getLogger(__name__)
        self.output_folder = "graph_citations"  # Default output folder for graph files
        os.makedirs(self.output_folder, exist_ok=True)  # Ensure output folder exists

    def add_citation(self, citing_title, citing_url, cited_by_url, cited_title=None, citing_doi=None, cited_doi=None):
        """Adds a citation relationship to the graph.

        Nodes are created for both citing and cited papers.  If DOIs are available,
        they are used as primary node identifiers.  Titles and URLs are stored as
        node attributes.

        Args:
            citing_title (str): Title of the citing paper.
            citing_url (str, optional): URL of the citing paper.
            cited_by_url (str, optional): URL of the cited paper's "Cited by" page.
            cited_title (str, optional): Title of the cited paper (if known). Defaults to None.
            citing_doi (str, optional): DOI of the citing paper. Defaults to None.
            cited_doi (str, optional): DOI of the cited paper. Defaults to None.

        """
        citing_node_id = citing_doi if citing_doi else citing_url or citing_title  # DOI preferred as ID
        self.graph.add_node(
            citing_node_id, title=citing_title, url=citing_url, doi=citing_doi
        )  # Store title, URL, DOI as attributes

        cited_node_id = cited_doi if cited_doi else cited_by_url or cited_title or "Unknown Title"  # DOI preferred as ID
        cited_title = cited_title or cited_by_url or "Unknown Title"
        self.graph.add_node(
            cited_node_id, title=cited_title, url=cited_by_url, doi=cited_doi
        )  # Store title, URL, DOI as attributes

        if citing_node_id != cited_node_id:
            self.graph.add_edge(citing_node_id, cited_node_id)
            self.logger.debug(f"Added citation edge from '{citing_title}' to '{cited_title}'")
        else:
            self.logger.debug(f"Skipped self-citation for '{citing_title}'")

    def save_graph(self, filename="citation_graph.graphml"):
        """Saves the citation graph to a GraphML file in the 'graph_citations' folder.

        Args:
            filename (str, optional): The base filename to save the graph to.
                                     Defaults to "citation_graph.graphml".  Will be saved in 'graph_citations' folder.

        """
        full_filename = os.path.join(self.output_folder, filename)  # Save in output folder
        try:
            nx.write_graphml(self.graph, full_filename)
            self.logger.info(
                f"Citation graph saved to {full_filename} (GraphML format). "
                f"You can visualize it using tools like Gephi or Cytoscape for interactive exploration."
            )  # Note about visualization tools
        except Exception as e:
            self.logger.error(f"Error saving graph to {full_filename}: {e}", exc_info=True)

    def load_graph(self, filename="citation_graph.graphml"):
        """Loads a citation graph from a GraphML file in the 'graph_citations' folder.

        Handles FileNotFoundError and general exceptions during graph loading
        by starting with an empty graph and logging an error message.

        Args:
            filename (str, optional): The base filename to load the graph from.
                                     Defaults to "citation_graph.graphml". Will be loaded from 'graph_citations' folder.

        """
        full_filename = os.path.join(self.output_folder, filename)  # Load from output folder
        try:
            self.graph = nx.read_graphml(full_filename)
            self.logger.info(f"Graph loaded from {full_filename}")
        except FileNotFoundError:
            self.logger.warning(f"Graph file not found: {full_filename}. Starting with an empty graph.")
            self.graph = nx.DiGraph()  # Initialize empty graph if file not found
        except Exception as e:  # Catch XML parsing errors or other issues during loading
            self.logger.error(f"Error loading graph from {full_filename}: {e}. Starting with an empty graph.", exc_info=True)
            self.graph = nx.DiGraph()  # Initialize empty graph on error

    def calculate_degree_centrality(self):
        """Calculates and stores in-degree and out-degree centrality as node attributes."""
        in_degree_centrality = nx.in_degree_centrality(self.graph)
        out_degree_centrality = nx.out_degree_centrality(self.graph)
        nx.set_node_attributes(self.graph, in_degree_centrality, "in_degree_centrality")
        nx.set_node_attributes(self.graph, out_degree_centrality, "out_degree_centrality")
        self.logger.info("Calculated and stored degree centrality measures.")

    def visualize_graph(self, filename="citation_graph.png", layout="spring", filter_by_centrality: Optional[float] = None):
        """Visualizes the citation graph and saves it to a PNG file in 'graph_citations' folder.

        Nodes are sized based on their in-degree centrality.

        Args:
            filename (str, optional): The base filename to save the visualization to
                                     (as a PNG image). Defaults to "citation_graph.png". Will be saved in 'graph_citations' folder.
            layout (str, optional):  Layout algorithm to use for visualization.
                                      Options: 'spring' (default), 'circular', 'kamada_kawai'.
                                      Defaults to 'spring'.
            filter_by_centrality (float, optional):  Minimum in-degree centrality value to display nodes.
                                                     Nodes with centrality below this threshold will be filtered out.
                                                     Defaults to None (no filtering).

        """
        full_filename = os.path.join(self.output_folder, filename)  # Save in output folder
        try:
            if not self.graph.nodes():
                self.logger.warning("Graph is empty, no visualization to create.")
                return

            self.calculate_degree_centrality()  # Calculate centrality before visualization

            plt.figure(figsize=(12, 12))  # Adjust figure size as needed

            # Layout selection
            layout_functions = {
                "spring": nx.spring_layout,
                "circular": nx.circular_layout,
                "kamada_kawai": nx.kamada_kawai_layout,
                # Add more layouts here if needed
            }
            layout_func = layout_functions.get(layout, nx.spring_layout)  # Default to spring if layout is invalid
            pos = layout_func(self.graph)

            # Node size based on in-degree centrality (adjust multiplier as needed)
            node_size = [
                v * 5000 for v in nx.get_node_attributes(self.graph, "in_degree_centrality").values()
            ]  # Multiplier for visibility

            # Node filtering based on centrality
            nodes_to_draw = self.graph.nodes()  # Default to all nodes
            if filter_by_centrality is not None:
                nodes_to_draw = [
                    node
                    for node, centrality in nx.get_node_attributes(self.graph, "in_degree_centrality").items()
                    if centrality >= filter_by_centrality
                ]
                subgraph = self.graph.subgraph(nodes_to_draw)  # Create subgraph with filtered nodes
            else:
                subgraph = self.graph  # Use the full graph if no filtering

            nx.draw(
                subgraph,  # Draw the subgraph (or full graph if no filtering)
                pos,
                with_labels=False,  # Labels can clutter large graphs
                node_size=[
                    node_size[list(self.graph.nodes()).index(n)] for n in subgraph.nodes()
                ],  # Size nodes based on their original centrality in full graph
                node_color="skyblue",
                arrowsize=10,
                alpha=0.7,
            )
            title = "Citation Graph Visualization (Node Size by In-Degree Centrality)"
            if filter_by_centrality is not None:
                title += f" - Centrality Filter >= {filter_by_centrality}"  # Add filter info to title
            plt.title(title)
            plt.savefig(full_filename)  # Save to output folder
            self.logger.info(
                f"Citation graph visualization saved to {full_filename} (Layout: {layout}, Node size reflects citation count"
                + (f", Filtered by centrality >= {filter_by_centrality})" if filter_by_centrality is not None else ")")
            )  # Updated log with layout and filter info
            plt.close()  # Close the figure to free memory
        except Exception as e:
            self.logger.error(f"Error during graph visualization: {e}", exc_info=True)
            self.logger.warning("Graph visualization failed.")

    def generate_default_visualizations(self, base_filename="citation_graph"):
        """Generates default visualizations of the citation graph with different layouts.

        Saves PNG files to the 'graph_citations' folder for spring, circular, and kamada_kawai layouts.

        Args:
            base_filename (str, optional): Base filename for the visualization files.
                                            Layout name will be appended to this base name.
                                            Defaults to "citation_graph".

        """
        layouts = ["spring", "circular", "kamada_kawai"]
        for layout in layouts:
            filename = f"{base_filename}_{layout}_layout.png"
            self.visualize_graph(filename=filename, layout=layout)
        self.logger.info(
            f"Generated default visualizations in '{self.output_folder}' folder: {', '.join([f'{base_filename}_{layout}_layout.png' for layout in layouts])}"
        )


# google_scholar_research_tool.py
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
    parser.add_argument(
        "--log_level", default="DEBUG", choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"], help="Logging level."
    )  # Added log level argument

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
    parser.add_argument(
        "--graph_layout", default="spring", choices=["spring", "circular", "kamada_kawai"], help="Graph visualization layout."
    )  # Added graph layout option
    parser.add_argument(
        "--centrality_filter", type=float, default=None, help="Filter graph visualization by centrality (>=)."
    )  # Centrality filter

    args = parser.parse_args()

    # --- Input Validation ---
    if not args.query and not args.author_profile:
        parser.error("Error: Either a query or --author_profile must be provided.")
    if args.num_results <= 0:
        parser.error("Error: --num_results must be a positive integer.")
    if args.max_depth < 0:
        parser.error("Error: --max_depth cannot be negative.")
    if args.year_low is not None and not (1000 <= args.year_low <= 2100):
        parser.error("Error: --year_low must be a valid year (1000-2100).")
    if args.year_high is not None and not (1000 <= args.year_high <= 2100):
        parser.error("Error: --year_high must be a valid year (1000-2100).")
    if args.centrality_filter is not None and args.centrality_filter < 0:
        parser.error("Error: --centrality_filter must be a non-negative value.")

    # --- Logging Configuration ---
    logging.basicConfig(
        format="%(asctime)s | %(levelname)s | %(filename)s:%(lineno)d | %(funcName)s | %(message)s",
        level=args.log_level.upper(),  # Set log level from argument
    )

    proxy_manager = ProxyManager()
    fetcher = Fetcher(proxy_manager=proxy_manager)
    data_handler = DataHandler()
    graph_builder = GraphBuilder()

    await data_handler.create_table()
    os.makedirs(args.pdf_dir, exist_ok=True)

    try:  # Top-level error handling
        try:
            await proxy_manager.get_working_proxies()
        except NoProxiesAvailable:
            logging.error("No working proxies available. Exiting.")
            return

        if args.author_profile:
            author_data = await fetcher.fetch_author_profile(args.author_profile)
            if author_data:
                if args.json:
                    data_handler.save_to_json(author_data, args.output)
                else:  # Save author to csv if not json.
                    df = pd.DataFrame([author_data])
                    try:  # Output file error handling
                        df.to_csv(args.output, index=False)
                    except IOError as e:
                        logging.error(f"Error saving to CSV file '{args.output}': {e}", exc_info=True)
                        print(f"Error saving to CSV file. Check logs for details.")
                        return
                print(f"Author profile data saved to {args.output}")

                if args.recursive:
                    recursive_results = []
                    print("Recursively scraping author's publications...")
                    for pub in tqdm(author_data["publications"], desc="Fetching Publication Details", unit="pub"):
                        publication_detail = await fetcher.scrape_publication_details(pub["link"])  # Use new fetcher method
                        if publication_detail:
                            recursive_results.extend(publication_detail)  # Extend with list of results
                        await asyncio.sleep(random.uniform(1, 2))  # Polite delay

                    if recursive_results:
                        print(f"Recursively scraped {len(recursive_results)} publication details.")
                        if args.json:
                            try:  # Output file error handling for recursive results
                                data_handler.save_to_json(recursive_results, "recursive_" + args.output)  # Save to separate file
                            except IOError as e:
                                logging.error(
                                    f"Error saving recursive results to JSON file 'recursive_{args.output}': {e}", exc_info=True
                                )
                                print(f"Error saving recursive results to JSON file. Check logs.")
                        else:
                            df_recursive = pd.DataFrame(recursive_results)
                            try:  # Output file error handling for recursive results CSV
                                df_recursive.to_csv("recursive_" + args.output, index=False)  # Save to separate CSV
                            except IOError as e:
                                logging.error(
                                    f"Error saving recursive results to CSV file 'recursive_{args.output}': {e}", exc_info=True
                                )
                                print(f"Error saving recursive results to CSV file. Check logs.")
                        print(f"Recursive publication details saved to recursive_{args.output}")
                    else:
                        print("No publication details found during recursive scraping.")

        else:  # Main scraping logic for search queries
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
                # Pass advanced search parameters
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
                try:  # Output file error handling
                    data_handler.save_to_json(results, args.output)
                except IOError as e:
                    logging.error(f"Error saving to JSON file '{args.output}': {e}", exc_info=True)
                    print(f"Error saving to JSON file. Check logs for details.")
                    return
            else:
                try:  # Output file error handling
                    data_handler.save_to_csv(results, args.output)
                except IOError as e:
                    logging.error(f"Error saving to CSV file '{args.output}': {e}", exc_info=True)
                    print(f"Error saving to CSV file. Check logs for details.")
                    return
            logging.info(f"Successfully scraped and saved {len(results)} results in {args.output}")

            print(f"Citation graph: {graph_builder.graph.number_of_nodes()} nodes, {graph_builder.graph.number_of_edges()} edges")
            graph_builder.save_graph(args.graph_file)
            print(f"Citation graph saved to {args.graph_file}")

            graph_builder.generate_default_visualizations(
                base_filename=args.graph_file.replace(".graphml", "")
            )  # Generate default visualizations
            print(f"Citation graph visualizations saved to {graph_builder.output_folder} folder")

    except Exception as e:  # Top-level exception handler for any unhandled errors
        logging.critical(f"Unhandled exception in main(): {e}", exc_info=True)  # Log critical error with traceback
        print(
            f"A critical error occurred: {type(e).__name__} - {e}. Please check the logs for more details."
        )  # User-friendly error message

    finally:
        await fetcher.close()
        proxy_manager.log_proxy_performance()
        logging.info("--- Scraping process finished ---")  # End process log message


if __name__ == "__main__":
    asyncio.run(main())
