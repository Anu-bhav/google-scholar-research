# Google Scholar Scraper (Research Tool)

[![Python Version](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**Python tool to scrape Google Scholar efficiently. Features include: keyword search, PDF downloading (with DOI and fallback methods), citation network extraction, proxy rotation, and data export (CSV/JSON). Built with asyncio, httpx, and parsel.**

> [!WARNING]
> This project is currently in a state of "mostly functional," kind of like a slightly wonky robot butler – it _usually_ does what you ask, but sometimes it might bring you a sock instead of a cup of tea. This was also put together during a caffeine-fueled weekend, so please don't have _too_ high of expectations. Bug reports are greatly appreciated (and will be rewarded with virtual high-fives)!

## Features

- **Google Scholar Scraping:** Extracts search results for given queries from Google Scholar.
- **Advanced Search Parameters:** Supports searching by keywords, authors, publication names, and year ranges.
- **Data Extraction:** Parses and extracts key information from search results, including:
  - Title
  - Authors
  - Publication Information (venue, year)
  - Snippet/Abstract
  - Cited-by Count and Link
  - Related Articles Link
  - Article URL
  - DOI (if available)
  - Author Affiliations (basic extraction)
- **PDF Downloading:**
  - Attempts to download PDFs using DOI and Unpaywall API for Open Access papers.
  - Fallback PDF extraction directly from publisher pages for non-DOI papers.
  - Saves downloaded PDFs to a specified directory.
- **Citation Network Building:** Extracts citation information and builds a basic citation network graph using `networkx`.
- **Proxy Rotation:** Integrates with `free-proxy` library to rotate through free proxies for scraping (note: free proxies are unreliable for production use).
- **Asynchronous Scraping:** Uses `asyncio` and `httpx` for efficient and fast scraping.
- **Data Export:** Saves scraped data in CSV or JSON format.
- **Incremental Scraping:** Basic support to avoid re-scraping already retrieved results using a SQLite database.
- **Command-Line Interface (CLI):** User-friendly command-line interface for running scrapes with various options.

## Installation

**Clone the repository:**

    ```bash
    git clone [repository URL]
    cd scholar_scraper
    ```

**Install dependencies:**

    ```bash
    pip install -r requirements.txt
    ```

    Alternatively, install them individually:

    ```bash
    pip install httpx parsel free-proxy fake-useragent networkx pandas sqlite-utils httpx-caching
    ```

## Usage

Run `main.py` from the command line with your search query and options.

```bash
python main.py "<search query>" [options]
```

**Options:**

The following options can be used to customize your search and output:

- `query`: The search query you want to use (required, first argument).
- `-a` or `--authors`: Search for publications by specific author(s).
- `-p` or `--publication`: Search within a specific publication.
- `-l` or `--year_low`: Lower bound of the publication year range.
- `-u` or `--year_high`: Upper bound of the publication year range.
- `-n` or `--num_results`: Maximum number of results to retrieve (default: 10).
- `-o` or `--output`: Output file name (default: `results.csv`).
- `--json`: Output results in JSON format instead of CSV.
- `--pdf_dir`: Directory to save downloaded PDFs (default: `pdfs`).
- `--max_depth`: Maximum recursion depth for citation network scraping (default: 3).

## Example with more options:

```bash
python main.py "deep learning" -a "Yoshua Bengio" -l 2020 --json -o bengio_dl_2020.json --pdf_dir bengio_pdfs -n 30
```

**Dependencies Section:**

- Python 3.8+
- [httpx](https://www.python-httpx.org/)
- [parsel](https://parsel.readthedocs.io/en/latest/)
- [free-proxy](https://pypi.org/project/free-proxy/)
- [fake-useragent](https://pypi.org/project/fake-useragent/)
- [networkx](https://networkx.org/)
- [pandas](https://pandas.pydata.org/)

## Important Disclaimers

- **Terms of Service:** Scraping Google Scholar may violate their Terms of Service. Use this tool responsibly and at your own risk. Be aware that Google may block your IP address if you scrape too aggressively.
- **CAPTCHA:** Google Scholar employs CAPTCHAs to prevent bot activity. This scraper includes basic CAPTCHA detection, but bypassing CAPTCHAs reliably is very challenging and may be against Google's terms. You may encounter CAPTCHAs, especially with frequent use.
- **Free Proxies:** This tool uses free proxies, which are unreliable and often slow. For serious or large-scale scraping, consider using a reputable paid proxy service. Free proxies may expose your IP address or fail frequently.
- **Ethical Use:** Respect copyright and use scraped data ethically. Do not redistribute copyrighted material without permission. Use this tool for research, personal study, or purposes that comply with copyright law and website terms of service.
- **Rate Limiting:** The scraper includes delays between requests to be somewhat respectful of Google Scholar's servers. However, you may still need to adjust the scraping speed and delays depending on your needs and Google's rate limiting policies.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

**Disclaimer:** This tool is provided for educational and research purposes only. The author is not responsible for any misuse or consequences arising from the use of this software. Always use web scraping tools responsibly and ethically.
