"""
Tests for the AuthorProfileParser module.
"""

import unittest
from unittest.mock import MagicMock, patch

from google_scholar_scraper.exceptions import ParsingException

# Try to import the AuthorProfileParser, but mock it if not available yet
try:
    from google_scholar_scraper.author_profile_parser import AuthorProfileParser
except ImportError:
    # For testing purposes, we'll create a mock if the module doesn't exist yet
    AuthorProfileParser = MagicMock()


class TestAuthorProfileParser(unittest.TestCase):
    """Test cases for AuthorProfileParser class"""

    def setUp(self):
        """Set up test environment"""
        # Skip tests if using mock version
        if isinstance(AuthorProfileParser, MagicMock):
            self.skipTest("AuthorProfileParser module not available")

        self.parser = AuthorProfileParser()

        # Sample HTML for an author profile
        self.sample_profile_html = """
        <div id="gsc_prf_in">John Smith</div>
        <div class="gsc_prf_il">Computer Science Department, Example University</div>
        <div class="gsc_prf_il">Verified email at example.edu</div>
        <div id="gsc_prf_int">
            <a class="gsc_prf_inta" href="/citations?view_op=search_authors&amp;mauthors=label:machine_learning">Machine Learning</a>
            <a class="gsc_prf_inta" href="/citations?view_op=search_authors&amp;mauthors=label:artificial_intelligence">Artificial Intelligence</a>
        </div>
        <div id="gsc_rsb_st">
            <table>
                <tr><th>Citations</th><th>h-index</th><th>i10-index</th></tr>
                <tr><td>1250</td><td>15</td><td>20</td></tr>
            </table>
        </div>
        <div id="gsc_a_b">
            <div class="gsc_a_tr">
                <div class="gsc_a_t">
                    <a href="/citations?view_op=view_citation&amp;citation_for_view=123456">Machine Learning Applications</a>
                    <div class="gs_gray">J Smith, A Johnson</div>
                    <div class="gs_gray">Journal of AI, 2022</div>
                </div>
                <div class="gsc_a_c"><a href="/citations?view_op=view_citation&amp;citation_for_view=123456">85</a></div>
            </div>
            <div class="gsc_a_tr">
                <div class="gsc_a_t">
                    <a href="/citations?view_op=view_citation&amp;citation_for_view=789012">Deep Neural Networks</a>
                    <div class="gs_gray">J Smith, B Williams</div>
                    <div class="gs_gray">Conference on AI, 2021</div>
                </div>
                <div class="gsc_a_c"><a href="/citations?view_op=view_citation&amp;citation_for_view=789012">42</a></div>
            </div>
        </div>
        <div id="gsc_cocit">
            <h3>Co-authors</h3>
            <div class="gsc_oci">
                <a href="/citations?user=abc123"><img src="photo1.jpg"></a>
                <span class="gsc_oci_name"><a href="/citations?user=abc123">Alice Johnson</a></span>
                <span class="gsc_oci_aff">Example University</span>
            </div>
            <div class="gsc_oci">
                <a href="/citations?user=def456"><img src="photo2.jpg"></a>
                <span class="gsc_oci_name"><a href="/citations?user=def456">Bob Williams</a></span>
                <span class="gsc_oci_aff">Another University</span>
            </div>
        </div>
        """

    @patch("google_scholar_scraper.author_profile_parser.Selector")
    def test_parse_profile_complete(self, mock_selector):
        """Test parse_profile method with complete author profile HTML"""
        # Skip if using mock version of AuthorProfileParser
        if isinstance(AuthorProfileParser, MagicMock):
            self.skipTest("AuthorProfileParser module not available")

        # Set up mock selector to return elements from sample HTML
        mock_instance = MagicMock()
        mock_selector.return_value = mock_instance

        # Set up mock returns for CSS selectors
        # Define mock publications (these will be the items iterated over)
        mock_pub1 = MagicMock()
        mock_pub1.css.side_effect = lambda s: MagicMock(
            get=lambda attr=None: {
                ".gsc_a_t a::text": "Machine Learning Applications",
                ".gsc_a_c a::text": "85",
                ".gsc_a_t a::attr(href)": "/citations?view_op=view_citation&citation_for_view=123456",
            }.get(s),
            getall=lambda: {".gs_gray::text": ["J Smith, A Johnson", "Journal of AI, 2022"]}.get(s, []),
        )

        mock_pub2 = MagicMock()
        mock_pub2.css.side_effect = lambda s: MagicMock(
            get=lambda attr=None: {
                ".gsc_a_t a::text": "Deep Neural Networks",
                ".gsc_a_c a::text": "42",
                ".gsc_a_t a::attr(href)": "/citations?view_op=view_citation&citation_for_view=789012",
            }.get(s),
            getall=lambda: {".gs_gray::text": ["J Smith, B Williams", "Conference on AI, 2021"]}.get(s, []),
        )

        # Define mock co-authors (for future use if co-author parsing is implemented)
        mock_coauthor1 = MagicMock()
        mock_coauthor1.css.side_effect = lambda s: MagicMock(
            get=lambda attr=None: "Alice Johnson"
            if s == ".gsc_oci_name a::text"
            else ("Example University" if s == ".gsc_oci_aff::text" else None)
        )
        mock_coauthor2 = MagicMock()
        mock_coauthor2.css.side_effect = lambda s: MagicMock(
            get=lambda attr=None: "Bob Williams"
            if s == ".gsc_oci_name a::text"
            else ("Another University" if s == ".gsc_oci_aff::text" else None)
        )

        # Main side_effect for mock_instance.css
        def css_main_side_effect(selector_str):
            if selector_str == ".gsc_a_tr":
                return [mock_pub1, mock_pub2]  # Return list of publication mocks
            elif selector_str == ".gsc_oci":  # For co-authors
                return [mock_coauthor1, mock_coauthor2]  # Return list of co-author mocks
            else:
                # For other selectors, return a mock that has .get() and .getall()
                # configured from dictionaries.
                mock_for_selector = MagicMock()
                get_map = {
                    "#gsc_prf_in::text": "John Smith",
                    "#gsc_rsb_st tr:nth-child(2) td:nth-child(1)::text": "1250",
                    "#gsc_rsb_st tr:nth-child(2) td:nth-child(2)::text": "15",
                    "#gsc_rsb_st tr:nth-child(2) td:nth-child(3)::text": "20",
                }
                getall_map = {
                    ".gsc_prf_il::text": ["Computer Science Department, Example University", "Verified email at example.edu"],
                    "#gsc_prf_int a.gsc_prf_inta::text": ["Machine Learning", "Artificial Intelligence"],
                }
                mock_for_selector.get.return_value = get_map.get(selector_str)
                mock_for_selector.getall.return_value = getall_map.get(selector_str, [])
                return mock_for_selector

        mock_instance.css.side_effect = css_main_side_effect

        # Call the method to test
        profile = self.parser.parse_profile(self.sample_profile_html)

        # Verify profile data
        self.assertEqual(profile["name"], "John Smith")
        self.assertEqual(profile["affiliation"], "Computer Science Department, Example University")
        self.assertEqual(profile["interests"], ["Machine Learning", "Artificial Intelligence"])
        self.assertEqual(profile["metrics"]["citations"], 1250)
        self.assertEqual(profile["metrics"]["h_index"], 15)
        self.assertEqual(profile["metrics"]["i10_index"], 20)
        self.assertEqual(len(profile["publications"]), 2)
        self.assertEqual(profile["publications"][0]["title"], "Machine Learning Applications")
        self.assertEqual(profile["publications"][0]["citation_count"], 85)
        self.assertEqual(len(profile["co_authors"]), 2)
        self.assertEqual(profile["co_authors"][0]["name"], "Alice Johnson")
        self.assertEqual(profile["co_authors"][0]["affiliation"], "Example University")

    def test_parse_profile_empty_html(self):
        """Test parse_profile method with empty HTML"""
        # Skip if using mock version of AuthorProfileParser
        if isinstance(AuthorProfileParser, MagicMock):
            self.skipTest("AuthorProfileParser module not available")

        # Test with empty HTML
        with self.assertRaises(ParsingException):
            self.parser.parse_profile("")

    def test_parse_profile_missing_sections(self):
        """Test parse_profile method with HTML missing some sections"""
        # Skip if using mock version of AuthorProfileParser
        if isinstance(AuthorProfileParser, MagicMock):
            self.skipTest("AuthorProfileParser module not available")

        # Create HTML with minimal content (just name)
        minimal_html = """
        <div id="gsc_prf_in">John Smith</div>
        """

        # Mock the parser to handle this case
        with patch("google_scholar_scraper.author_profile_parser.Selector") as mock_selector:
            mock_instance = MagicMock()
            mock_selector.return_value = mock_instance

            # Set up mock returns for CSS selectors
            mock_instance.css.side_effect = lambda selector_arg: MagicMock(  # Use a distinct name for the lambda arg
                get=lambda attr=None: "John Smith" if selector_arg == "#gsc_prf_in::text" else None,
                getall=lambda: [],  # Corrected key
            )

            # Call the method to test
            profile = self.parser.parse_profile(minimal_html)

            # Verify minimal profile data
            self.assertEqual(profile["name"], "John Smith")
            self.assertIsNone(profile["affiliation"])
            self.assertEqual(profile["interests"], [])
            self.assertEqual(profile["metrics"]["citations"], 0)
            self.assertEqual(profile["metrics"]["h_index"], 0)
            self.assertEqual(profile["metrics"]["i10_index"], 0)
            self.assertEqual(profile["publications"], [])
            self.assertEqual(profile["co_authors"], [])


if __name__ == "__main__":
    unittest.main()
