import urllib


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
