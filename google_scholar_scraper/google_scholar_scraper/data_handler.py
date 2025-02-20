# data_handler.py
import asyncio
import json
import logging
import sqlite3
from typing import Dict, List, Optional

import aiosqlite
import pandas as pd


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
