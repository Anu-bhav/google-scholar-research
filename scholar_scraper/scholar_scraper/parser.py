# parser.py
import logging
import re

from exceptions import ParsingException
from parsel import Selector


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
