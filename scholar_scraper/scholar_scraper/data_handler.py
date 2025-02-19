# data_handler.py
import json
import logging
import sqlite3
from typing import Dict, List

import aiosqlite
import pandas as pd


class DataHandler:
    def __init__(self, db_name="scholar_data.db"):
        self.db_name = db_name
        self.logger = logging.getLogger(__name__)

    async def create_table(self):
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

    async def insert_result(self, result):
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
            except sqlite3.IntegrityError:
                # self.logger.debug(f"Duplicate entry skipped: {result['article_url']}")
                pass  # Silently handle duplicates.

    async def result_exists(self, article_url):
        async with aiosqlite.connect(self.db_name) as db:
            async with db.execute("SELECT 1 FROM results WHERE article_url = ?", (article_url,)) as cursor:
                return await cursor.fetchone() is not None

    def save_to_csv(self, results: List[Dict], filename: str):
        if not results:
            self.logger.warning("No results to save.")
            return
        try:
            df = pd.DataFrame(results)
            df.to_csv(filename, index=False, encoding="utf-8")
        except Exception as e:
            self.logger.error("Error writing the csv", exc_info=True)

    def save_to_json(self, results, filename):
        with open(filename, "w", encoding="utf-8") as jsonfile:
            json.dump(results, jsonfile, indent=4)

    def save_to_dataframe(self, results):
        return pd.DataFrame(results)
