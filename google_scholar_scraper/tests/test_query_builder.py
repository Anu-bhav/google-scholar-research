"""
Tests for the QueryBuilder module.
"""

import unittest
import urllib.parse

from google_scholar_scraper.query_builder import QueryBuilder


class TestQueryBuilder(unittest.TestCase):
    """Test cases for QueryBuilder class"""

    def setUp(self):
        """Initialize QueryBuilder instance for tests"""
        self.query_builder = QueryBuilder()
        self.base_url = "https://scholar.google.com/scholar"

    def test_init_default_base_url(self):
        """Test __init__ method sets default base URL correctly"""
        self.assertEqual(self.query_builder.base_url, self.base_url)

    def test_init_custom_base_url(self):
        """Test __init__ method sets custom base URL correctly"""
        custom_url = "https://custom.google.com/scholar"
        query_builder = QueryBuilder(base_url=custom_url)
        self.assertEqual(query_builder.base_url, custom_url)

    def test_build_url_basic_query(self):
        """Test build_url method with basic keyword query"""
        url = self.query_builder.build_url(
            query="machine learning",
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
        )

        # Parse URL to extract and verify query parameters
        parsed_url = urllib.parse.urlparse(url)
        query_params = urllib.parse.parse_qs(parsed_url.query)

        self.assertEqual(parsed_url.netloc, "scholar.google.com")
        self.assertEqual(parsed_url.path, "/scholar")
        self.assertIn("q", query_params)
        self.assertEqual(query_params["q"][0], "machine learning")
        self.assertIn("start", query_params)
        self.assertEqual(query_params["start"][0], "0")

    def test_build_url_with_all_parameters(self):
        """Test build_url method with all parameters specified"""
        url = self.query_builder.build_url(
            query="neural networks",
            start=10,
            authors="Andrew Ng",
            publication="Nature",
            year_low=2020,
            year_high=2023,
            phrase="deep learning",
            exclude="supervised",
            title="transformer",
            author="attention",
            source="journal",
        )

        # Parse URL to extract and verify query parameters
        parsed_url = urllib.parse.urlparse(url)
        query_params = urllib.parse.parse_qs(parsed_url.query)

        # Check base components
        self.assertEqual(parsed_url.netloc, "scholar.google.com")
        self.assertEqual(parsed_url.path, "/scholar")

        # Construct expected query string components
        expected_query_parts = [
            "neural networks",  # from query="neural networks"
            '"deep learning"',  # from phrase="deep learning"
            "-supervised",  # from exclude="supervised"
            "title:transformer",  # from title="transformer" (QueryBuilder uses "title:")
            "author:attention",  # from author="attention" (QueryBuilder uses "author:")
            "source:journal",  # from source="journal" (QueryBuilder uses "source:")
        ]

        # Verify query components are present in the constructed URL
        self.assertIn("q", query_params)
        query_str = query_params["q"][0]
        # Check that all expected parts are in the query string
        for part in expected_query_parts:
            self.assertIn(part, query_str)

        # Also check the specific parameters like as_sauthors, as_ylo, as_yhi, as_publication
        self.assertIn("as_sauthors", query_params)
        self.assertEqual(query_params["as_sauthors"][0], "Andrew Ng")
        self.assertIn("as_publication", query_params)
        self.assertEqual(query_params["as_publication"][0], "Nature")
        self.assertIn("as_ylo", query_params)
        self.assertEqual(query_params["as_ylo"][0], "2020")
        self.assertIn("as_yhi", query_params)
        self.assertEqual(query_params["as_yhi"][0], "2023")

        # Verify pagination parameter
        self.assertIn("start", query_params)
        self.assertEqual(query_params["start"][0], "10")

    def test_build_url_special_characters(self):
        """Test build_url handles special characters correctly"""
        url = self.query_builder.build_url(
            query="C++ & Python",
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
        )

        parsed_url = urllib.parse.urlparse(url)
        query_params = urllib.parse.parse_qs(parsed_url.query)

        # Verify the URL encoding is handled correctly
        self.assertIn("C%2B%2B", url)
        self.assertIn("%26", url)

    def test_build_author_profile_url(self):
        """Test build_author_profile_url constructs correct URL"""
        author_id = "XYZ123456789"
        url = self.query_builder.build_author_profile_url(author_id)

        self.assertIn(author_id, url)
        self.assertIn("user=", url)
        self.assertTrue(url.startswith("https://scholar.google.com/citations"))


if __name__ == "__main__":
    unittest.main()
