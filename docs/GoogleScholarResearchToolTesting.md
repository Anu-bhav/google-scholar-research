# Google Scholar Research Tool Testing Tasks

This document outlines the testing strategy for each module in the Google Scholar Research Tool.

## Test Execution Environment and Commands

This project uses `pytest` for testing. The testing environment and dependencies are managed using `uv`.

**Prerequisites:**

1.  Ensure `uv` is installed.
2.  From the project root directory (`google-scholar-research-tool/`), install the project package in editable mode and its dependencies:
    ```bash
    uv pip install -e ./google_scholar_scraper
    ```
    This command also installs test dependencies listed in `google_scholar_scraper/tests/requirements-test.txt`.

**Running Tests:**

- **Using `uv run pytest` (Recommended for individual files/directories):**
  To run all tests in a specific file (e.g., `test_data_handler.py`):

  ```bash
  uv run pytest -v google_scholar_scraper/tests/test_data_handler.py
  ```

  To run all tests in the `tests` directory:

  ```bash
  uv run pytest -v google_scholar_scraper/tests/
  ```

- **Using the `run_tests.py` script:**
  The project includes a `google_scholar_scraper/tests/run_tests.py` script which can also execute tests, primarily using `pytest` by default.
  ```bash
  python google_scholar_scraper/tests/run_tests.py
  ```
  This script can also target specific, pre-defined modules by name (see the script's usage comments).

**Async Tests:**
Many tests, particularly those involving database interactions or network operations, are asynchronous and require `pytest-asyncio`. The test setup pattern for async fixtures that has proven reliable in this environment is:

- Define `async def` fixtures that `return` the required object (e.g., a `DataHandler` instance).
- Test functions that use these fixtures must also be `async def`, be decorated with `@pytest.mark.asyncio`, and must `await` the fixture parameter to get the actual object instance. Example:

  ```python
  @pytest.fixture
  async def my_async_fixture(tmp_path):
      # ... async setup using tmp_path ...
      obj = MyObject()
      await obj.async_init()
      return obj

  @pytest.mark.asyncio
  async def test_something(my_async_fixture): # my_async_fixture is a coroutine here
      actual_obj = await my_async_fixture     # Await to get the MyObject instance
      await actual_obj.do_something_async()
  ```

  This pattern ensures that fixtures are correctly resolved and temporary resources (like databases in `tmp_path`) are available throughout the test execution.

## 1. QueryBuilder Module Testing

### Unit Tests

- [ ] Test `__init__` method for correct initialization
- [ ] Test `build_url` method:
  - [ ] Basic keyword query construction
  - [ ] URL construction with all parameters (authors, publication, year ranges, etc.)
  - [ ] Special character handling and URL encoding
  - [ ] Edge cases: empty query, only year range
  - [ ] Pagination parameter handling
- [ ] Test `build_author_profile_url` method:
  - [ ] Valid author ID
  - [ ] Optional parameters handling

## 2. ProxyManager Module Testing

### Unit Tests

- [ ] Test `__init__` method with different configuration parameters
- [ ] Test `_load_blacklist` method:
  - [ ] Existing valid blacklist file
  - [ ] Non-existent blacklist file
  - [ ] Corrupted/invalid JSON blacklist
  - [ ] Expired blacklist entries
- [ ] Test `_save_blacklist` method for correct JSON writing
- [ ] Test `_initialize_proxy_stats` for correct initialization of proxy metrics
- [ ] Test `_test_proxy` method:
  - [ ] Successful HTTP/HTTPS connections
  - [ ] Connection failures
  - [ ] Timeout handling
  - [ ] 403/Forbidden responses
  - [ ] CAPTCHA detection scenarios
- [ ] Test `get_working_proxies` method:
  - [ ] Return cached proxies if within refresh interval
  - [ ] Proxy filtering logic
  - [ ] Blacklist integration
- [ ] Test `refresh_proxies` method
- [ ] Test `get_random_proxy` method:
  - [ ] Behavior with available proxies
  - [ ] Handling when no proxies are available
  - [ ] Proxy selection logic
- [ ] Test `remove_proxy` method for blacklisting behavior
- [ ] Test `mark_proxy_failure` for correct error tracking
- [ ] Test `mark_proxy_success` for success metrics update
- [ ] Test `get_proxy_performance_data` for correct data structure
- [ ] Test `log_proxy_performance` for logging format

### Integration Tests

- [ ] Test interaction with `Fetcher` class
- [ ] Test blacklist persistence across sessions

## 3. Parser Module Testing

### Unit Tests

- [ ] Test `parse_results` method:
  - [ ] HTML with multiple search results
  - [ ] HTML with no search results
  - [ ] HTML with partial data (missing elements)
- [ ] Test `parse_raw_items` for correct item container identification
- [ ] Test extraction methods with various input formats:
  - [ ] `extract_title`: valid, missing, special characters
  - [ ] `extract_authors`: single, multiple, with/without links
  - [ ] `extract_publication_info`: different formats (journal, year, pages)
  - [ ] `extract_snippet`: valid, missing
  - [ ] `extract_cited_by`: valid count, missing info
  - [ ] `extract_related_articles_url`: valid, missing
  - [ ] `extract_article_url`: various link types
  - [ ] `extract_doi`: presence/absence of DOI
  - [ ] `extract_direct_pdf_url`: various PDF link formats
- [ ] Test `find_next_page` for pagination link detection
- [ ] Test error handling with malformed HTML

### Integration Tests

- [ ] Test with `Fetcher` to verify correct HTML processing

## 4. AuthorProfileParser Module Testing

### Unit Tests

- [ ] Test `parse_profile` method:
  - [ ] Complete author profile HTML
  - [ ] Profiles with missing sections
  - [ ] Extraction of author metrics
  - [ ] Co-authors list parsing
  - [ ] Publications list extraction
- [ ] Test error handling for malformed profiles

### Integration Tests

- [ ] Test with `Fetcher` for complete author profile workflow

## 5. Fetcher Module Testing

### Unit Tests

- [ ] Test `__init__` for correct initialization of attributes
- [ ] Test `_create_client` for correct aiohttp session creation
- [ ] Test `_get_delay` for proper delay generation
- [ ] Test `fetch_page` method:
  - [ ] Successful request scenarios
  - [ ] Network errors (connection, timeout)
  - [ ] HTTP error status handling (403, 429, 500s)
  - [ ] CAPTCHA detection and handling
  - [ ] Metrics tracking (success/failure counts)
- [ ] Test `fetch_pages` for multiple URL handling
- [ ] Test `download_pdf` method:
  - [ ] Successful download
  - [ ] Non-PDF content handling
  - [ ] Error handling and retries
- [ ] Test `scrape_pdf_link` method:
  - [ ] Unpaywall API integration
  - [ ] Direct PDF link detection
  - [ ] Publisher-specific PDF extraction
- [ ] Test `extract_cited_title` for citation title extraction
- [ ] Test `fetch_cited_by_page` for citation network traversal
- [ ] Test `close` method for proper session cleanup
- [ ] Test `calculate_rps` and `calculate_etr` for metrics calculation
- [ ] Test `scrape` method for overall orchestration
- [ ] Test `fetch_author_profile` for author data retrieval
- [ ] Test `scrape_publication_details` for publication data

### Integration Tests

- [ ] Test full scraping workflow with controlled proxy responses
- [ ] Test integration with parsers and data handler

## 6. DataHandler Module Testing

### Unit Tests

- [ ] Test `__init__` method for database connection
- [ ] Test `create_table` for schema creation
- [ ] Test `insert_result` method:
  - [ ] New result insertion
  - [ ] Duplicate handling
  - [ ] Data type mapping
- [ ] Test `result_exists` for correct result checking
- [ ] Test `save_to_csv` for correct file generation
- [ ] Test `save_to_json` for proper JSON formatting
- [ ] Test `save_to_dataframe` for DataFrame structure

### Integration Tests

- [ ] Test data flow from fetcher/parser to storage
- [ ] Test export functionality with real data

## 7. GraphBuilder Module Testing

### Unit Tests

- [ ] Test `__init__` for graph initialization
- [ ] Test `add_citation` method:
  - [ ] New nodes and edges
  - [ ] Existing nodes connection
  - [ ] Node attribute handling
- [ ] Test `save_graph` method for GraphML output
- [ ] Test `load_graph` method:
  - [ ] Valid GraphML loading
  - [ ] Error handling for invalid files
- [ ] Test `calculate_degree_centrality` for network analysis
- [ ] Test `visualize_graph` method:
  - [ ] Different layout algorithms
  - [ ] Centrality filtering
  - [ ] Node styling and visualization
- [ ] Test `generate_default_visualizations` for multi-layout output

### Integration Tests

- [ ] Test graph building with data from scraping workflow

## 8. Utility Functions Testing

### Unit Tests

- [ ] Test `get_random_delay` for range compliance
- [ ] Test `get_random_user_agent` for user agent generation
- [ ] Test `detect_captcha` method:
  - [ ] Known CAPTCHA HTML detection
  - [ ] Non-CAPTCHA HTML handling
  - [ ] Empty/None input handling

## 9. Main Function Testing

### Integration/E2E Tests

- [ ] Test CLI argument parsing with various combinations
- [ ] Test workflow with different search scenarios:
  - [ ] Basic keyword search
  - [ ] Author profile scraping
  - [ ] Recursive author profile scraping
  - [ ] Search with filters and constraints
- [ ] Test error handling for common failure scenarios
- [ ] Test output file generation and formats

## 10. probe-proxy.py Testing

### Unit Tests

- [ ] Test proxy finding functionality
- [ ] Test proxy testing methods
- [ ] Test result collection and filtering

### Integration Tests

- [ ] Test end-to-end proxy discovery and validation
- [ ] Test integration with main tool's proxy requirements
