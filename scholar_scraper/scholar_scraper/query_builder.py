# query_builder.py
import urllib.parse


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
