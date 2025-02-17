# scholar_scraper/scholar_scraper/data_handler.py
import csv
import json
import pandas as pd
import sqlite3


class DataHandler:
    def __init__(self, db_name="scholar_data.db"):
        self.db_name = db_name
        self.conn = sqlite3.connect(self.db_name)
        self.create_table()

    def create_table(self):
        cursor = self.conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS results (
                title TEXT,
                authors TEXT,
                publication_info TEXT,
                snippet TEXT,
                cited_by_count INTEGER,
                related_articles_url TEXT,
                article_url TEXT UNIQUE,  -- Ensure URLs are unique
                pdf_url TEXT,
                pdf_path TEXT,
                doi TEXT,
                affiliations TEXT,
                cited_by_url TEXT
            )
        """)
        self.conn.commit()

    def insert_result(self, result):
        cursor = self.conn.cursor()
        try:
            cursor.execute(
                """
                INSERT INTO results (title, authors, publication_info, snippet, cited_by_count,
                related_articles_url, article_url, pdf_url, pdf_path, doi, affiliations, cited_by_url)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    result["title"],
                    ",".join(result["authors"]),  # Convert list to string
                    json.dumps(result["publication_info"]),  # convert dict to string
                    result["snippet"],
                    result["cited_by_count"],
                    result["related_articles_url"],
                    result["article_url"],
                    result.get("pdf_url"),  # use get to handle missing values
                    result.get("pdf_path"),
                    result.get("doi"),
                    ",".join(result.get("affiliations", [])),  # affiliations to string
                    result.get("cited_by_url"),
                ),
            )
            self.conn.commit()
        except sqlite3.IntegrityError:
            # Handle the case where the URL already exists (duplicate)
            pass

    def result_exists(self, article_url):
        cursor = self.conn.cursor()
        cursor.execute("SELECT 1 FROM results WHERE article_url = ?", (article_url,))
        return cursor.fetchone() is not None

    def save_to_csv(self, results, filename):
        """Saves the results to a CSV file."""
        if not results:
            print("No results to save.")
            return

        with open(filename, "w", newline="", encoding="utf-8") as csvfile:
            fieldnames = results[0].keys()  # Get fieldnames from the first result
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(results)

    def save_to_json(self, results, filename):
        """Saves the results to a JSON file."""
        with open(filename, "w", encoding="utf-8") as jsonfile:
            json.dump(results, jsonfile, indent=4)

    def save_to_dataframe(self, results):
        """Converts the results to a Pandas DataFrame."""
        return pd.DataFrame(results)
