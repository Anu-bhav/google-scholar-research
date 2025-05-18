# Google Scholar Research Tool - Technical Documentation

## 1. Code Organization

### 1.1 Project Structure

google_scholar_scraper/ ├── google_scholar_scraper/ # Package directory ├── pdfs/ # Downloaded PDFs storage ├── graph_citations/ # Generated graph visualizations ├── proxy_blacklist.json # Persistent proxy blacklist ├── scholar_data.db # SQLite database for scraped data ├── google_scholar_research_tool.py # Main entry point └── pyproject.toml # Project metadata

### 1.2 Module Organization

The codebase follows a modular structure with clear separation of concerns:

- **Exception Definitions**: Custom exceptions for specific error conditions
- **Model Definitions**: Enums and data structures
- **Utility Functions**: Helper functions for common operations
- **Core Classes**: Each representing a distinct responsibility
  - `QueryBuilder`: URL construction
  - `ProxyManager`: Proxy lifecycle management
  - `Parser`: Search results parsing
  - `AuthorProfileParser`: Author profile parsing
  - `Fetcher`: Network operations
  - `DataHandler`: Data persistence
  - `GraphBuilder`: Citation network visualization

## 2. API Documentation

### 2.1 QueryBuilder

#### Methods

- `__init__(base_url="https://scholar.google.com/scholar")`: Initializes with Google Scholar base URL
- `build_url(query, start, authors, publication, year_low, year_high, phrase, exclude, title, author, source)`: Constructs search URL with parameters
- `build_author_profile_url(author_id)`: Constructs author profile URL

### 2.2 ProxyManager

#### Methods

- `__init__(timeout, refresh_interval, blacklist_duration, num_proxies, blacklist_file)`: Initializes proxy manager with configuration
- `_load_blacklist()`: Loads blacklisted proxies from JSON file
- `_save_blacklist()`: Persists blacklist to JSON file
- `_initialize_proxy_stats(proxy)`: Sets up performance tracking for a proxy
- `_test_proxy(proxy)`: Tests if a proxy works and measures latency
- `get_working_proxies()`: Returns a list of working proxies
- `refresh_proxies()`: Forces refresh of the proxy list
- `get_random_proxy()`: Returns a random working proxy
- `remove_proxy(proxy)`: Blacklists and removes a proxy
- `mark_proxy_failure(proxy, error_type)`: Records a proxy failure with categorization
- `mark_proxy_success(proxy)`: Records a successful proxy usage
- `get_proxy_performance_data()`: Returns proxy performance metrics
- `log_proxy_performance()`: Logs proxy performance statistics

### 2.3 Parser

#### Methods

- `__init__()`: Initializes the parser with logging
- `parse_results(html_content, include_raw_item)`: Extracts structured data from search results
- `parse_raw_items(html_content)`: Returns raw HTML item containers
- `extract_title(item_selector)`: Extracts paper title
- `extract_authors(item_selector)`: Extracts authors and affiliations
- `extract_publication_info(item_selector)`: Extracts publication and year
- `extract_snippet(item_selector)`: Extracts result snippet
- `extract_cited_by(item_selector)`: Extracts citation count and URL
- `extract_related_articles_url(item_selector)`: Extracts related articles URL
- `extract_article_url(item_selector)`: Extracts article URL
- `extract_doi(item_selector)`: Extracts DOI if available
- `extract_direct_pdf_url(item_selector)`: Extracts direct PDF link if available
- `find_next_page(html_content)`: Finds next page link

### 2.4 AuthorProfileParser

#### Methods

- `__init__()`: Initializes the author profile parser with logging
- `parse_profile(html_content)`: Extracts structured data from author profile

### 2.5 Fetcher

#### Methods

- `__init__(proxy_manager, min_delay, max_delay, max_retries, rolling_window_size)`: Initializes with configuration
- `_create_client()`: Creates an aiohttp client session
- `_get_delay()`: Gets a random delay within configured range
- `fetch_page(url, retry_count)`: Fetches a single page with retry logic
- `fetch_pages(urls)`: Fetches multiple pages concurrently
- `download_pdf(url, filename)`: Downloads a PDF with retry logic
- `scrape_pdf_link(doi, paper_url)`: Attempts to find PDF link via multiple methods
- `extract_cited_title(cited_by_url)`: Extracts title of citing paper
- `fetch_cited_by_page(url, proxy_manager, depth, max_depth, graph_builder)`: Recursively fetches citation network
- `close()`: Closes the HTTP client session
- `calculate_rps()`: Calculates requests per second
- `calculate_etr(rps, total_results, results_collected)`: Estimates time remaining
- `scrape(query, authors, publication, year_low, year_high, num_results, pdf_dir, max_depth, graph_builder, data_handler, phrase, exclude, title, author, source)`: Main scraping orchestration
- `fetch_author_profile(author_id)`: Fetches and parses author profile
- `scrape_publication_details(publication_url)`: Scrapes details of a specific publication

### 2.6 DataHandler

#### Methods

- `__init__(db_name)`: Initializes with database name
- `create_table()`: Creates the results table in SQLite
- `insert_result(result)`: Inserts a result into the database
- `result_exists(article_url)`: Checks if a result already exists
- `save_to_csv(results, filename)`: Exports results to CSV
- `save_to_json(results, filename)`: Exports results to JSON
- `save_to_dataframe(results)`: Converts results to pandas DataFrame

### 2.7 GraphBuilder

#### Methods

- `__init__()`: Initializes graph builder
- `add_citation(citing_title, citing_url, cited_by_url, cited_title, citing_doi, cited_doi)`: Adds a citation to the graph
- `save_graph(filename)`: Saves graph in GraphML format
- `load_graph(filename)`: Loads graph from GraphML file
- `calculate_degree_centrality()`: Calculates centrality metrics
- `visualize_graph(filename, layout, filter_by_centrality)`: Creates visualization with specified parameters
- `generate_default_visualizations(base_filename)`: Generates visualizations with different layouts

## 3. Database Schema

### 3.1 `results` Table

| Column               | Type      | Description                                   |
|----------------------|-----------|-----------------------------------------------|
| title                | TEXT      | Paper title                                   |
| authors              | TEXT      | Comma-separated list of authors               |
| publication_info     | TEXT      | JSON with publication name and year           |
| snippet              | TEXT      | Result snippet/abstract                       |
| cited_by_count       | INTEGER   | Number of citations                           |
| related_articles_url | TEXT      | URL to related articles                       |
| article_url          | TEXT      | URL to the article page (UNIQUE)              |
| pdf_url              | TEXT      | URL to PDF if available                       |
| pdf_path             | TEXT      | Local path to downloaded PDF                  |
| doi                  | TEXT      | Digital Object Identifier                     |
| affiliations         | TEXT      | Comma-separated list of author affiliations   |
| cited_by_url         | TEXT      | URL to "Cited by" page                        |

## 4. Command-Line Interface

The tool provides a comprehensive command-line interface with the following options:

usage: google_scholar_research_tool.py [-h] [-a AUTHORS] [-p PUBLICATION] [-l YEAR_LOW] [-u YEAR_HIGH] [-n NUM_RESULTS] [-o OUTPUT] [--json] [--pdf_dir PDF_DIR] [--max_depth MAX_DEPTH] [--graph_file GRAPH_FILE] [--log_level {DEBUG,INFO,WARNING,ERROR,CRITICAL}] [--phrase PHRASE] [--exclude EXCLUDE] [--title TITLE] [--author AUTHOR] [--source SOURCE] [--min_citations MIN_CITATIONS] [--author_profile AUTHOR_PROFILE] [--recursive] [--graph_layout {spring,circular,kamada_kawai}] [--centrality_filter CENTRALITY_FILTER] [query]

## 5. Performance Considerations

### 5.1 Proxy Management

- Free proxies have variable reliability
- Proxy performance tracking helps select better proxies
- Blacklisting prevents repeated use of failing proxies
- Performance metrics include:
  - Success/failure counts
  - Average latency
  - CAPTCHA encounter rate
  - Connection error frequency

### 5.2 Rate Limiting and Politeness

- Random delays between requests (2-5 seconds by default)
- User-agent rotation to avoid detection
- CAPTCHA detection to prevent account blocking
- Asynchronous architecture for better resource utilization

### 5.3 Memory Usage

- Citation networks can grow large with deep recursion
- PDF downloads are streamed to disk in chunks
- Database used for persistent storage instead of keeping all results in memory

## 6. Error Handling

### 6.1 Network Errors

- Connection errors: Retry with different proxy
- Timeout errors: Mark proxy as slow, retry with different proxy
- HTTP 403/429: Likely rate limiting, increase delay and change proxy
- CAPTCHA detection: Remove proxy, pause, and retry with new proxy

### 6.2 Parsing Errors

- Missing elements: Return None or empty value instead of failing
- Structure changes: Raise ParsingException for critical failures
- HTML parsing errors: Log and continue with next result when possible

### 6.3 File System Errors

- PDF directory creation: Create if not exists
- File writing permissions: Exception handling with meaningful error messages
- Database access: Connection pooling and retry logic

## 7. Logging

The system uses Python's logging module with configurable levels:
- DEBUG: Detailed information for debugging
- INFO: Confirmation of expected behavior
- WARNING: Indication of potential issues
- ERROR: Error conditions preventing specific operations
- CRITICAL: Critical errors causing program failure

Log format includes timestamp, level, file:line, function name, and message.

## 8. Testing Strategy

See the accompanying `tasklist.md` for detailed testing plans.

## 9. Security Considerations

### 9.1 Data Protection

- Local storage of all scraped data
- No transmission to external services (except Unpaywall API)
- No storage of sensitive credentials

### 9.2 API Usage

- Unpaywall API used with proper attribution
- Respect for robots.txt where applicable
- Conservative rate limiting

### 9.3 Input Validation

- Command-line argument validation
- URL parameter sanitization
- File path security for PDF storage