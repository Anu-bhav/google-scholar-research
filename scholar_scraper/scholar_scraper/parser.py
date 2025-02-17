# scholar_scraper/scholar_scraper/parser.py
import logging
import re

from parsel import Selector  # Import Selector from parsel

from .exceptions import ParsingException

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(filename)s:%(lineno)d | %(funcName)s | %(message)s", level=logging.DEBUG
)


class Parser:
    def __init__(self):
        self.logger = logging.getLogger(__name__)

    def parse_results(self, html_content):
        """Parses the search results from a Google Scholar results page."""
        selector = Selector(text=html_content)  # use parsel Selector here.
        results = []

        for item_selector in selector.css("div.gs_ri"):  # parsel css selector
            try:
                title = self.extract_title(item_selector)
                authors, affiliations = self.extract_authors(item_selector)  # Get affiliations
                publication_info = self.extract_publication_info(item_selector)
                snippet = self.extract_snippet(item_selector)
                cited_by_count, cited_by_url = self.extract_cited_by(item_selector)  # get url
                related_articles_url = self.extract_related_articles_url(item_selector)
                article_url = self.extract_article_url(item_selector)
                doi = self.extract_doi(item_selector)  # Extract DOI

                results.append(
                    {
                        "title": title,
                        "authors": authors,
                        "affiliations": affiliations,  # Add affiliations
                        "publication_info": publication_info,
                        "snippet": snippet,
                        "cited_by_count": cited_by_count,
                        "cited_by_url": cited_by_url,  # add cited_by_url
                        "related_articles_url": related_articles_url,
                        "article_url": article_url,
                        "doi": doi,  # Add DOI
                        "pdf_url": None,  # Initialize pdf_url
                        "pdf_path": None,  # Initialize pdf_path
                    }
                )
            except Exception as e:
                self.logger.error(f"Error parsing an item: {e}")  # Log individual parsing errors
                raise ParsingException(f"Error during parsing of an item: {e}") from e
        return results

    def extract_title(self, item_selector):  # item_selector is parsel.Selector now
        title_tag = item_selector.css("h3.gs_rt")  # parsel css selector
        if title_tag:
            link_element = title_tag.css("a::text").get()  # parsel css selector + text extraction
            if link_element:
                return link_element
            else:
                return title_tag.xpath("./text()").get().strip()  # parsel xpath for text without children
        return None

    def extract_authors(self, item_selector):  # item_selector is parsel.Selector now
        authors_tag = item_selector.css("div.gs_a")  # parsel css selector
        if authors_tag:
            author_text = authors_tag.xpath("./text()").get()  # parsel xpath for text
            if author_text:  # check if author_text is not None
                # Use regular expressions for more robust author extraction.
                match = re.match(r"(.*?)\s+-", author_text)
                if match:
                    authors_part = match.group(1).strip()
                    authors = [a.strip() for a in authors_part.split(",") if a.strip()]

                    # Handle "et al" by checking the original text
                    if "…" in authors_part or "..." in authors_part:
                        authors.append("et al.")  # Add "et al." if ellipsis found
                    affiliations = []
                    # Try to extract affiliation (VERY HTML-dependent)
                    parts = [part.strip() for part in author_text.split("-") if part.strip()]
                    if len(parts) > 1:
                        affiliation_text = parts[0].strip()
                        affiliation_parts = [aff.strip() for aff in affiliation_text.split(",") if aff.strip()]
                        affiliations = affiliation_parts[len(authors) :]  # get remaining parts

                    return authors, affiliations
        return [], []

    def extract_publication_info(self, item_selector):  # item_selector is parsel.Selector now
        pub_info_tag = item_selector.css("div.gs_a")  # parsel css selector
        if pub_info_tag:
            pub_info_text = pub_info_tag.xpath("./text()").get()  # parsel xpath for text
            if pub_info_text:  # check if pub_info_text is not None
                # Use regular expressions for more robust author extraction.
                match = re.search(r"-\s*(.*?)\s*-\s*(.*)", pub_info_text)
                if match:
                    publication = match.group(1).strip()
                    year_match = re.search(r"\b\d{4}\b", match.group(2))
                    year = int(year_match.group(0)) if year_match else None
                    return {"publication": publication, "year": year}
        return {}

    def extract_snippet(self, item_selector):  # item_selector is parsel.Selector now
        snippet_tag = item_selector.css("div.gs_rs")  # parsel css selector
        return (
            snippet_tag.xpath("./text()").get().strip() if snippet_tag.xpath("./text()").get() else None
        )  # parsel xpath for text

    def extract_cited_by(self, item_selector):  # item_selector is parsel.Selector now
        cited_by_tag = item_selector.css("a[href*=scholar\?cites]")  # parsel css selector with attribute filter
        if cited_by_tag:
            cited_by_text = cited_by_tag.xpath("./text()").get()  # parsel xpath for text
            match = re.search(r"\d+", cited_by_text) if cited_by_text else None  # check cited_by_text is not None
            cited_by_count = int(match.group(0)) if match else 0
            cited_by_url = (
                "https://scholar.google.com" + cited_by_tag.attrib["href"] if cited_by_tag else None
            )  # parsel attrib for href
            return cited_by_count, cited_by_url
        return 0, None

    def extract_related_articles_url(self, item_selector):  # item_selector is parsel.Selector now
        related_tag = item_selector.css("a[href*=scholar\?q=related]")  # parsel css selector with attribute filter
        if related_tag:
            return "https://scholar.google.com" + related_tag.attrib["href"]  # parsel attrib for href
        return None

    def extract_article_url(self, item_selector):  # item_selector is parsel.Selector now
        link_tag = item_selector.css("h3.gs_rt a")  # parsel chained css selector
        return link_tag.attrib["href"] if link_tag else None  # parsel attrib for href

    def extract_doi(self, item_selector):  # item_selector is parsel.Selector now
        """Extracts the DOI from the result item."""
        # Look for DOI links in the 'gs_or_ggsm' div, which usually contains links to full texts.
        links_div = item_selector.css("div.gs_or_ggsm")  # parsel css selector
        if links_div:
            for link in links_div.css("a"):  # parsel chained css selector
                href = link.attrib["href"]  # parsel attrib for href
                if href:
                    # A DOI link typically starts with 'https://doi.org/'
                    match = re.search(r"https?://doi\.org/(10\.[^/]+/[^/]+)", href)
                    if match:
                        return match.group(1)  # Return the captured DOI (group 1)
        return None

    def find_next_page(self, html_content):
        """Finds the URL for the next page of results."""
        selector = Selector(text=html_content)  # parsel Selector here.
        next_button = selector.css('a[aria-label="Next"]')  # parsel css selector with attribute filter
        if next_button:
            return next_button.attrib["href"]  # parsel attrib for href
        return None

    def extract_pdf_url(self, item_selector):  # item_selector is parsel.Selector now
        # Very basic example - needs to be adapted to Google Scholar's HTML
        pdf_link = item_selector.css('a[href*=".pdf"]')  # parsel css selector with attribute filter for .pdf
        if pdf_link:
            return pdf_link.attrib["href"]  # parsel attrib for href

        # Check for known publishers and call specialized functions:
        article_link_tag = item_selector.css("h3.gs_rt a")  # parsel chained css selector
        if article_link_tag:
            article_url = article_link_tag.attrib["href"]  # parsel attrib for href
            if "ieeexplore.ieee.org" in article_url:
                return self.extract_pdf_from_ieee(article_url)  # Call IEEE-specific function
            # Add elif blocks for other publishers (ACM, Springer, etc.)

        return None

    def extract_pdf_from_ieee(self, article_url):
        # Placeholder - needs to be implemented to fetch and parse the IEEE page
        # This is VERY website-specific and likely to require frequent updates.
        print(f"Attempting to extract PDF from IEEE: {article_url} (Placeholder)")
        return None
