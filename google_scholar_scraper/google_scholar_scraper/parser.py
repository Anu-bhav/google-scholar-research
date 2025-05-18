# parser.py
import logging
import re

from parsel import Selector

from google_scholar_scraper.exceptions import ParsingException


class Parser:
    def __init__(self):
        self.logger = logging.getLogger(__name__)

    def parse_results(self, html_content, include_raw_item=False):
        selector = Selector(text=html_content)
        results = []

        for item_selector in selector.css("div.gs_ri"):
            try:
                title = self.extract_title(item_selector)
                authors = self.extract_authors(item_selector)  # Changed: extract_authors will only return authors
                publication_info = self.extract_publication_info(item_selector)  # This will now handle pub name and year
                # Affiliations are not explicitly extracted as a separate top-level field in this structure
                # publication_info = self.extract_publication_info(item_selector) # Removed duplicate call
                snippet = self.extract_snippet(item_selector)
                cited_by_info = self.extract_cited_by(item_selector)
                related_articles_url = self.extract_related_articles_url(item_selector)
                article_url = self.extract_article_url(item_selector)
                doi = self.extract_doi(item_selector)

                result = {
                    "title": title,
                    "authors": authors,
                    # "affiliations": affiliations, # Removed, as pub_info now handles this context
                    "publication_info": publication_info,
                    "snippet": snippet,
                    "cited_by_count": cited_by_info.get("count"),
                    "cited_by_url": cited_by_info.get("url"),
                    "related_articles_url": related_articles_url,
                    "article_url": article_url,
                    "doi": doi,
                    "pdf_url": None,  # Initialize
                    "pdf_path": None,  # Initialize
                }

                # Skip adding the result if it seems like a "No results found" entry
                # A more robust check might be needed depending on variations
                if title is None and article_url is None and not authors and not publication_info.get("publication"):
                    # If it's just a div.gs_ri with text like "No results found.", most fields will be None/empty.
                    # Check if the item_selector itself contains indicative text if other fields are also None.
                    raw_text_content = "".join(item_selector.xpath(".//text()").getall()).lower()
                    if "no results found" in raw_text_content or "did not match any articles" in raw_text_content:
                        continue  # Skip this pseudo-item

                results.append(result)
                # The include_raw_item logic needs to be re-evaluated if it's meant
                # to change the output structure (e.g., return tuples).
                # For now, ensuring items are added.
                # if include_raw_item:
                #    pass # Or modify the appended result if needed

            except Exception as e:
                self.logger.error(f"Error parsing an item: {e}")
                raise ParsingException(f"Error during parsing: {e}") from e

        next_page_url = self.find_next_page(html_content)
        # To make next_page_url available to the caller, parse_results could return (results, next_page_url)
        # For now, tests will be adjusted to call find_next_page separately or this structure will be revisited.
        # Let's assume for now the primary return is the list of result dicts.
        return results

    def parse_raw_items(self, html_content):
        selector = Selector(text=html_content)
        return selector.css("div.gs_ri")

    def extract_title(self, item_selector):
        try:
            title_tag = item_selector.css("h3.gs_rt")
            if title_tag:
                link_tag = title_tag.css("a")
                if link_tag:
                    # Get all text nodes within the <a> tag, including those in nested tags like <b>
                    link_text_parts = link_tag.css("::text").getall()
                    if link_text_parts:
                        return "".join(link_text_parts).strip()
                    return None  # Link tag exists but is empty
                else:
                    # No <a> tag, try to get text directly from h3.gs_rt
                    direct_text = title_tag.xpath("./text()").get()
                    return direct_text.strip() if direct_text else None
            return None
        except Exception as e:
            self.logger.error(f"Error extracting title: {e}")
            return None

    def extract_authors(self, item_selector):
        try:
            authors_tag = item_selector.css("div.gs_a")
            if authors_tag:
                # Get all descendant text nodes, join them, and then clean up
                # This ensures text from <a> tags (for authors) and other nested elements is included.
                author_text_all_nodes = authors_tag.xpath("descendant-or-self::text()").getall()
                author_text = "".join(author_text_all_nodes).strip()
                # Replace non-breaking spaces with regular spaces for consistent splitting
                author_text = author_text.replace("\xa0", " ")
                # Consolidate multiple spaces
                author_text = re.sub(r"\s+", " ", author_text).strip()
                if author_text:
                    # Authors are typically before the first " - "
                    authors_segment = author_text.split(" - ", 1)[0]
                    authors_list = [a.strip() for a in authors_segment.split(",") if a.strip()]
                    # Handle "et al." scenarios
                    add_et_al = False
                    if authors_list:
                        last_author = authors_list[-1]
                        if "ΓÇª" in last_author or "..." in last_author:
                            # Clean up the last author name by removing ellipsis characters
                            authors_list[-1] = last_author.replace("ΓÇª", "").replace("...", "").strip()
                            # Remove empty string if stripping ellipsis results in one
                            if not authors_list[-1]:
                                authors_list.pop()
                            add_et_al = True
                        elif "ΓÇª" in authors_segment or "..." in authors_segment:  # Check segment if not in last author
                            add_et_al = True

                    if add_et_al and (not authors_list or authors_list[-1] != "et al."):
                        authors_list.append("et al.")

                    return authors_list
                return []  # Return empty list if author_text parsing fails
            return []  # Return empty list if authors_tag is not found
        except Exception as e:
            self.logger.error(f"Error extracting authors: {e}")
            return []  # Return empty list on exception

    def extract_publication_info(self, item_selector):
        try:
            pub_info_tag = item_selector.css("div.gs_a")
            if not pub_info_tag:  # Ensure the tag exists
                return {}

            # Get all text, including from within <a> tags for authors, etc.
            full_text_nodes = pub_info_tag.xpath("descendant-or-self::text()").getall()
            full_text = "".join(full_text_nodes).strip()
            full_text = full_text.replace("\xa0", " ")  # Replace non-breaking space
            full_text = re.sub(r"\s+", " ", full_text).strip()  # Consolidate multiple spaces

            if not full_text:
                return {}

            segments = full_text.split(" - ", 1)
            # We need at least authors AND pub_info part
            if len(segments) <= 1:
                return {}

            pub_year_segment = segments[1].strip()
            year_str = None
            publication_name = ""  # Default to empty

            best_year_match_obj = None
            for m in re.finditer(r"\b(\d{4})\b", pub_year_segment):
                best_year_match_obj = m  # Takes the last (rightmost) year

            if best_year_match_obj:
                year_str = best_year_match_obj.group(1)
                year_start_index = best_year_match_obj.start()
                year_end_index = best_year_match_obj.end()

                pre_year_text = pub_year_segment[:year_start_index].strip()
                if pre_year_text.endswith(","):
                    pre_year_text = pre_year_text[:-1].strip()

                post_year_text_segment = pub_year_segment[year_end_index:].strip()

                if pre_year_text:
                    publication_name = pre_year_text
                elif post_year_text_segment.startswith("-"):  # Check if there's content like " - site.com" after year
                    # Remove leading hyphen and potential space
                    publication_name = post_year_text_segment[1:].strip()
                    if publication_name.startswith("-"):  # Handle cases like "- - site.com"
                        publication_name = publication_name[1:].strip()
                # If pre_year_text is empty and post_year_text_segment doesn't start with " - ",
                # publication_name remains empty.

            else:  # No year found in pub_year_segment
                publication_name = pub_year_segment

            year = int(year_str) if year_str else None

            if publication_name == year_str:  # If pub name is just the year, it's not a real pub name
                publication_name = ""

            return {"publication": publication_name, "year": year}

        except Exception as e:
            self.logger.error(f"Error extracting publication info: {e}")
            return {}

    def extract_snippet(self, item_selector):
        try:
            snippet_tag = item_selector.css("div.gs_rs")
            if snippet_tag:
                # Get all text nodes, this will include text before and after <br> as separate items
                text_nodes = snippet_tag.xpath("descendant-or-self::text()").getall()
                # Join with spaces, then clean up multiple spaces and strip
                snippet_text = " ".join(node.strip() for node in text_nodes if node.strip())
                snippet_text = re.sub(r"\s+", " ", snippet_text).strip()
                return snippet_text if snippet_text else None
            return None
        except Exception as e:
            self.logger.error(f"Error extracting snippet: {e}")
            return None

    def extract_cited_by(self, item_selector):
        try:
            cited_by_tag = item_selector.css("a[href*='scholar?cites']")  # Corrected selector
            if cited_by_tag:
                cited_by_text = cited_by_tag.xpath("./text()").get()
                match = re.search(r"\d+", cited_by_text) if cited_by_text else None
                cited_by_count = int(match.group(0)) if match else 0
                cited_by_url_path = cited_by_tag.attrib.get("href")
                if cited_by_url_path:
                    if cited_by_url_path.startswith("http"):
                        cited_by_url = cited_by_url_path
                    else:
                        cited_by_url = f"https://scholar.google.com{cited_by_url_path}"
                else:
                    cited_by_url = None
                return {"count": cited_by_count, "url": cited_by_url}
            return {"count": 0, "url": None}
        except Exception as e:
            self.logger.error(f"Error extracting cited_by info: {e}")
            return {"count": 0, "url": None}

    def extract_related_articles_url(self, item_selector):
        try:
            # Look for links containing "?related=" and text "Related articles"
            # Reverting to CSS selector
            css_selector = 'div.gs_fl a[href*="?related="]'
            related_tags = item_selector.css(css_selector)
            # self.logger.info(f"DEBUG-RAU: Found {len(related_tags)} tags for CSS '{css_selector}' selector.") # DEBUG removed
            for idx, tag in enumerate(related_tags):
                tag_text_parts = tag.xpath(".//text()").getall()
                tag_text = "".join(tag_text_parts).strip().lower()
                # self.logger.info(f"DEBUG-RAU: Tag {idx} text: '{tag_text}', href: '{tag.attrib.get('href')}'") # DEBUG removed
                if "related articles" in tag_text:
                    href = tag.attrib.get("href")
                    if href:
                        if href.startswith("http"):  # Ensure URL is absolute
                            return href
                        else:
                            return f"https://scholar.google.com{href}"
            # Fallback or alternative selectors if needed can be added here
            return None
        except Exception as e:
            self.logger.error(f"Error extracting related articles URL: {e}")
            return None

    def extract_article_url(self, item_selector):
        try:
            link_tag = item_selector.css("h3.gs_rt a")
            if link_tag:
                href = link_tag.attrib.get("href")
                # self.logger.info(f"DEBUG-EAU: Found link_tag for article_url. Tag: {link_tag.get()}, Href: {href}") # DEBUG removed
                return href
            else:
                # self.logger.info("DEBUG-EAU: No link_tag found for h3.gs_rt a.") # DEBUG removed
                return None
        except Exception as e:
            self.logger.error(f"Error extracting article URL: {e}")
            return None

    def extract_doi(self, item_selector):
        try:
            links_div = item_selector.css("div.gs_or_ggsm")
            if links_div:
                for link in links_div.css("a"):
                    href = link.attrib.get("href")  # Use .get() for safety
                    if href:
                        match = re.search(r"https?://doi\.org/(10\.[^/]+/[^/]+)", href)
                        if match:
                            return match.group(1)
            return None
        except Exception as e:
            self.logger.error(f"Error extracting DOI: {e}")
            return None

    def find_next_page(self, html_content):
        selector = Selector(text=html_content)
        # Try to find the "Next" link. Google might use different structures.
        # Option 1: Specific td.gs_n structure often seen
        next_button = selector.css('td.gs_n a[href*="start="]')
        if next_button and "Next" in next_button.xpath(".//text()").get(default="").strip():
            href = next_button.attrib.get("href")
            if href:
                return href if href.startswith("http") else f"https://scholar.google.com{href}"
            return None

        # Option 2: More general "Next" link, possibly with aria-label
        next_button_aria = selector.css('a[aria-label="Next"]')
        if next_button_aria:
            href_aria = next_button_aria.attrib.get("href")
            if href_aria:
                return href_aria if href_aria.startswith("http") else f"https://scholar.google.com{href_aria}"
            return None

        # Option 3: Link within a div with id="gs_n" then td a
        next_button_div_gsn = selector.css('div#gs_n td a[href*="start="]')
        # Check if the link specifically contains "Next" text, possibly within a <b> tag
        if next_button_div_gsn:
            # Iterate because selector.css can return multiple elements, though we expect one.
            for btn_candidate in next_button_div_gsn:
                # Check text within the <a> tag or its children like <b>
                button_text_content = "".join(btn_candidate.xpath(".//text()").getall()).strip()
                if "Next" in button_text_content:
                    href_div_gsn = btn_candidate.attrib.get("href")
                    if href_div_gsn:
                        return href_div_gsn if href_div_gsn.startswith("http") else f"https://scholar.google.com{href_div_gsn}"
                    return None

        # Option 4: Link with text "Next" within a common navigation area (original Option 3)
        # This might need adjustment based on actual HTML structure if the above fail
        # For now, relying on the more specific selectors.
        return None


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
                coauthor_href = coauthor.attrib.get("href")
                coauthor_link = f"https://scholar.google.com{coauthor_href}" if coauthor_href else None
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
                pub_link_href = pub.css(".gsc_a_at::attr(href)").get()
                link = f"https://scholar.google.com{pub_link_href}" if pub_link_href else None
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
