# scholar_scraper/scholar_scraper/query_builder.py
import urllib.parse


class QueryBuilder:
    def __init__(self, base_url="https://scholar.google.com/scholar"):
        self.base_url = base_url

    def build_url(self, query, start=0, authors=None, publication=None, year_low=None, year_high=None):
        """Builds a Google Scholar URL with various search parameters."""
        params = {
            "q": query,
            "start": start,
            "hl": "en",  # Language (English)
        }

        if authors:
            params["as_sauthors"] = authors  # Add authors parameter
        if publication:
            params["as_publication"] = publication
        if year_low:
            params["as_ylo"] = year_low
        if year_high:
            params["as_yhi"] = year_high

        encoded_params = urllib.parse.urlencode(params)
        return f"{self.base_url}?{encoded_params}"
