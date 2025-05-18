import logging
from typing import Any, Dict

from parsel import Selector  # Add this import

from google_scholar_scraper.exceptions import ParsingException


class AuthorProfileParser:
    def __init__(self):
        self.logger = logging.getLogger(__name__)

    def parse_profile(self, html_content: str) -> Dict[str, Any]:
        """
        Parses the HTML content of an author's profile page.
        """
        if not html_content:
            self.logger.warning("Attempted to parse empty HTML content for author profile.")
            raise ParsingException("Cannot parse empty HTML content for author profile.")

        selector = Selector(text=html_content)
        self.logger.info("Parsing author profile page.")

        profile_data: Dict[str, Any] = {}

        # Name
        profile_data["name"] = selector.css("#gsc_prf_in::text").get()

        # Affiliation and Email
        profile_info_elements = selector.css(".gsc_prf_il::text").getall()
        profile_data["affiliation"] = None
        profile_data["email"] = None  # Initialize email as None

        if profile_info_elements:
            # First element is usually affiliation
            if len(profile_info_elements) > 0:
                profile_data["affiliation"] = profile_info_elements[0].strip()

            # Look for email, often marked or containing '@'
            for item_text in profile_info_elements:
                item_text_stripped = item_text.strip()
                if "Verified email at" in item_text_stripped:
                    profile_data["email"] = item_text_stripped.replace("Verified email at", "").strip()
                    break
                elif "@" in item_text_stripped and not profile_data["email"]:  # Basic check if not already found
                    # This might need more sophisticated extraction if email is not clearly separated
                    profile_data["email"] = item_text_stripped
                    # Potentially break if confident, or continue if multiple @ symbols could appear legitimately

        # Interests
        interests_list = selector.css("#gsc_prf_int a.gsc_prf_inta::text").getall()
        profile_data["interests"] = (
            [interest.strip() for interest in interests_list if interest.strip()] if interests_list else []
        )

        # Metrics
        citations_text = selector.css("#gsc_rsb_st tr:nth-child(2) td:nth-child(1)::text").get()
        h_index_text = selector.css("#gsc_rsb_st tr:nth-child(2) td:nth-child(2)::text").get()
        i10_index_text = selector.css("#gsc_rsb_st tr:nth-child(2) td:nth-child(3)::text").get()

        try:
            citations = int(citations_text.strip()) if citations_text else 0
        except ValueError:
            citations = 0  # Default if conversion fails
        try:
            h_index = int(h_index_text.strip()) if h_index_text else 0
        except ValueError:
            h_index = 0
        try:
            i10_index = int(i10_index_text.strip()) if i10_index_text else 0
        except ValueError:
            i10_index = 0

        profile_data["metrics"] = {
            "citations": citations,  # Key used in test
            "h_index": h_index,
            "i10_index": i10_index,
        }
        # Publications
        publications_list = []
        publication_rows = selector.css(".gsc_a_tr")  # Get all publication row selectors
        for row_selector in publication_rows:
            pub_data = {}
            pub_data["title"] = row_selector.css(".gsc_a_t a::text").get()

            # Authors and Journal/Year are often in consecutive .gs_gray elements
            gray_elements = row_selector.css(".gs_gray::text").getall()
            if len(gray_elements) >= 1:
                pub_data["authors"] = gray_elements[0].strip()
            else:
                pub_data["authors"] = None

            if len(gray_elements) >= 2:
                pub_data["source"] = gray_elements[1].strip()  # e.g., "Journal of AI, 2022"
            else:
                pub_data["source"] = None

            citation_count_text = row_selector.css(".gsc_a_c a::text").get()
            try:
                pub_data["citation_count"] = int(citation_count_text.strip()) if citation_count_text else 0
            except ValueError:
                pub_data["citation_count"] = 0

            # Article URL (from title link)
            pub_data["article_url"] = row_selector.css(".gsc_a_t a::attr(href)").get()

            if pub_data["title"]:  # Only add if a title was found
                publications_list.append(pub_data)

        profile_data["publications"] = publications_list

        # Co-authors
        co_authors_list = []
        coauthor_entries = selector.css(".gsc_oci")  # Get all co-author entry selectors
        for entry_selector in coauthor_entries:
            coauthor_data = {}
            coauthor_data["name"] = entry_selector.css(".gsc_oci_name a::text").get()
            coauthor_data["affiliation"] = entry_selector.css(".gsc_oci_aff::text").get()  # Based on test mock
            coauthor_data["profile_url"] = entry_selector.css(".gsc_oci_name a::attr(href)").get()

            if coauthor_data["name"]:  # Only add if a name was found
                co_authors_list.append(coauthor_data)

        profile_data["co_authors"] = co_authors_list

        return profile_data
