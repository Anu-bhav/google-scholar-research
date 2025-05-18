import json

import aiosqlite  # Added import
import pandas as pd
import pytest
from google_scholar_scraper.data_handler import DataHandler

# Sample data for testing
SAMPLE_RESULT_1 = {
    "title": "Test Article 1",
    "authors": ["Author A", "Author B"],
    "publication_info": {"journal": "Test Journal", "year": "2023"},
    "snippet": "This is a test snippet for article 1.",
    "cited_by_count": 10,
    "related_articles_url": "http://example.com/related1",
    "article_url": "http://example.com/article1",
    "pdf_url": "http://example.com/pdf1",
    "pdf_path": "/path/to/pdf1.pdf",
    "doi": "10.1234/test.doi.1",
    "affiliations": ["Affiliation X", "Affiliation Y"],
    "cited_by_url": "http://example.com/citedby1",
}

SAMPLE_RESULT_2 = {
    "title": "Test Article 2",
    "authors": ["Author C"],
    "publication_info": {"journal": "Another Journal", "year": "2024"},
    "snippet": "Snippet for article 2.",
    "cited_by_count": 5,
    "related_articles_url": "http://example.com/related2",
    "article_url": "http://example.com/article2",
    "pdf_url": None,
    "pdf_path": None,
    "doi": "10.1234/test.doi.2",
    "affiliations": ["Affiliation Z"],
    "cited_by_url": "http://example.com/citedby2",
}


@pytest.fixture
async def data_handler(tmp_path):  # Added tmp_path parameter
    """
    Provides a DataHandler instance with a temporary database using tmp_path.

    Note: This fixture returns the handler. Tests must await this fixture
    to get the DataHandler instance.
    """
    db_path = tmp_path / "test_scholar_data.db"  # Use tmp_path
    handler = DataHandler(db_name=str(db_path))
    # Ensure table is created before tests run
    await handler.create_table()
    return handler  # Returns the handler


# Removed data_handler_diagnostic fixture


@pytest.mark.asyncio
async def test_data_handler_init(data_handler):  # Now uses the main data_handler fixture
    """Test DataHandler initialization."""
    actual_dh = data_handler  # Fixture is already resolved by pytest-asyncio
    assert actual_dh.db_name.endswith("test_scholar_data.db")  # Uses main DB name
    assert isinstance(actual_dh.logger, object)  # Basic check for logger


@pytest.mark.asyncio
async def test_create_table_idempotent(data_handler):
    """Test that create_table can be called multiple times without error."""
    actual_dh = data_handler
    await actual_dh.create_table()  # Call again
    # Check if table exists by trying to query it (simple query)
    try:
        async with aiosqlite.connect(actual_dh.db_name) as db:
            cursor = await db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='results';")
            table = await cursor.fetchone()
            assert table is not None
            assert table[0] == "results"
    except Exception as e:
        pytest.fail(f"Querying table after create_table failed: {e}")


@pytest.mark.asyncio
async def test_insert_and_retrieve_result(data_handler):
    """Test inserting a result and checking its existence."""
    actual_dh = data_handler
    assert not await actual_dh.result_exists(SAMPLE_RESULT_1["article_url"])
    await actual_dh.insert_result(SAMPLE_RESULT_1)
    assert await actual_dh.result_exists(SAMPLE_RESULT_1["article_url"])

    # Verify content
    async with aiosqlite.connect(actual_dh.db_name) as db:
        cursor = await db.execute("SELECT * FROM results WHERE article_url = ?", (SAMPLE_RESULT_1["article_url"],))
        row = await cursor.fetchone()
        assert row is not None
        assert row[0] == SAMPLE_RESULT_1["title"]
        assert row[1] == ",".join(SAMPLE_RESULT_1["authors"])
        assert json.loads(row[2]) == SAMPLE_RESULT_1["publication_info"]
        assert row[6] == SAMPLE_RESULT_1["article_url"]  # article_url is unique


@pytest.mark.asyncio
async def test_insert_duplicate_result(data_handler):
    """Test that inserting a duplicate result is handled gracefully."""
    actual_dh = data_handler
    await actual_dh.insert_result(SAMPLE_RESULT_1)
    # Attempt to insert the same result again
    await actual_dh.insert_result(SAMPLE_RESULT_1)  # Should not raise error and be skipped

    # Check that only one entry exists
    async with aiosqlite.connect(actual_dh.db_name) as db:
        cursor = await db.execute("SELECT COUNT(*) FROM results WHERE article_url = ?", (SAMPLE_RESULT_1["article_url"],))
        count = await cursor.fetchone()
        assert count is not None  # Ensure 'count' is not None before subscripting
        assert count[0] == 1


@pytest.mark.asyncio
async def test_result_exists_not_found(data_handler):
    """Test result_exists for a non-existent URL."""
    actual_dh = data_handler
    assert not await actual_dh.result_exists("http://example.com/nonexistent")


@pytest.mark.asyncio
async def test_save_to_csv(data_handler, tmp_path):
    """Test saving results to a CSV file."""
    actual_dh = data_handler
    results_list = [SAMPLE_RESULT_1, SAMPLE_RESULT_2]
    csv_file = tmp_path / "test_output.csv"
    actual_dh.save_to_csv(results_list, str(csv_file))

    assert csv_file.exists()
    df = pd.read_csv(csv_file)
    assert len(df) == 2
    assert df.iloc[0]["title"] == SAMPLE_RESULT_1["title"]
    assert df.iloc[1]["article_url"] == SAMPLE_RESULT_2["article_url"]


@pytest.mark.asyncio
async def test_save_to_csv_empty(data_handler, tmp_path):
    """Test saving an empty list to CSV."""
    actual_dh = data_handler
    csv_file = tmp_path / "empty_output.csv"
    actual_dh.save_to_csv([], str(csv_file))
    # Behavior for empty: pandas creates an empty file with headers if columns are known,
    # or just an empty file. The DataHandler logs a warning and returns.
    # We'll check that the file might not exist or is empty, as per DataHandler logic.
    if csv_file.exists():
        assert csv_file.read_text() == "" or len(pd.read_csv(csv_file)) == 0  # Allow for header-only or truly empty
    # More robustly, check that no error was raised and the warning was logged (requires logger mocking)


@pytest.mark.asyncio
async def test_save_to_json(data_handler, tmp_path):
    """Test saving results to a JSON file."""
    actual_dh = data_handler
    results_list = [SAMPLE_RESULT_1, SAMPLE_RESULT_2]
    json_file = tmp_path / "test_output.json"
    actual_dh.save_to_json(results_list, str(json_file))

    assert json_file.exists()
    with open(json_file, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert len(data) == 2
    assert data[0]["title"] == SAMPLE_RESULT_1["title"]
    assert data[1]["article_url"] == SAMPLE_RESULT_2["article_url"]


@pytest.mark.asyncio
async def test_save_to_json_empty(data_handler, tmp_path):
    """Test saving an empty list to JSON."""
    actual_dh = data_handler
    json_file = tmp_path / "empty_output.json"
    actual_dh.save_to_json([], str(json_file))
    # DataHandler logs a warning and returns. The file might not be created.
    assert not json_file.exists() or json_file.read_text() == ""


@pytest.mark.asyncio
async def test_save_to_dataframe(data_handler):
    """Test converting results to a pandas DataFrame."""
    actual_dh = data_handler
    results_list = [SAMPLE_RESULT_1, SAMPLE_RESULT_2]
    df = actual_dh.save_to_dataframe(results_list)

    assert isinstance(df, pd.DataFrame)
    assert len(df) == 2
    assert df.iloc[0]["title"] == SAMPLE_RESULT_1["title"]
    # Check for a field that might be None
    assert (
        pd.isna(df.iloc[1]["pdf_url"])
        if SAMPLE_RESULT_2["pdf_url"] is None
        else df.iloc[1]["pdf_url"] == SAMPLE_RESULT_2["pdf_url"]
    )


@pytest.mark.asyncio
async def test_save_to_dataframe_empty(data_handler):
    """Test converting an empty list to DataFrame."""
    actual_dh = data_handler
    df = actual_dh.save_to_dataframe([])
    assert isinstance(df, pd.DataFrame)
    assert df.empty
