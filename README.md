# Google Scholar Research Tool 🚀🎓

[![Python Version](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Google Scholar](https://img.shields.io/badge/Google%20Scholar-blue)](https://scholar.google.com/)

**A research tool for efficiently gathering and analyzing data from Google Scholar. With advanced search, including publications, citations, author profiles and other features like PDF downloads, citation analysis, and proxy rotation (CAPTCHAs Bypass). ⚡️**

> [!WARNING]
> This project is currently in a state of "mostly functional," kind of like a slightly wonky robot butler – it _usually_ does what you ask, but sometimes it might bring you a sock instead of a cup of tea. This was also put together during a caffeine-fueled weekend, so please don't have _too_ high of expectations. It's still WIP. Bug reports are greatly appreciated (and will be rewarded with virtual high-fives)!

## ✨ Features

- **Comprehensive Google Scholar Scraping:** Extract detailed search results, going beyond basic information.
- **Advanced Search:** Refine your searches with precision:
  - Keywords 🔎
  - Authors 🧑‍🔬
  - Publications 📰
  - Year Ranges 📅
  - Exact Phrases 💬
  - Keyword Exclusion 🚫
  - Field-Specific Searches (title, author, source) 🎯
  - Minimum Citation Count Filtering ⭐
- **Author Profile Scraping:** Dive deep into an author's work:
  - Fetch author details (name, affiliation, interests).
  - List co-authors.
  - Retrieve key metrics (total citations, h-index, i10-index).
  - Extract a list of publications.
  - _Optional:_ Recursive scraping of publication details.
- **PDF Downloading:**
  - Prioritizes Open Access papers via Unpaywall API.
  - Intelligent fallback to direct publisher page scraping.
  - Organized PDF storage.
- **Citation Network Analysis:**
  - Builds a citation graph to visualize research connections.
  - Configurable depth for citation exploration.
    **Graph Visualization Options:**
    - **Layout Algorithms:** Choose from `spring`, `circular`, and `kamada_kawai` layouts for different graph perspectives.
    - **Centrality Filtering:** Focus visualizations on the most influential papers by filtering nodes based on their in-degree centrality.
- **Robustness and Reliability:**
  - **Smart Proxy Rotation:** Automatically switches proxies on failures (429, 403, connection errors). **Enhanced proxy management includes performance tracking for better proxy selection.**
  - **CAPTCHA Detection:** Identifies CAPTCHAs and pauses to avoid getting blocked.
  - **Error Handling:** Gracefully handles various network and parsing issues.
- **Performance:**
  - **Asynchronous Operations:** Uses `asyncio` and `aiohttp` for high concurrency.
  - **Rate Limiting:** Built-in delays to respect Google Scholar's servers.
- **Data Management:**
  - **Database Integration:** Stores scraped data in an SQLite database to prevent duplicates.
  - **Flexible Output:** Export results to CSV or JSON.
- **User-Friendly CLI:** Easy-to-use command-line interface with clear options.
- **Progress Tracking:** Real-time progress bar with insightful statistics:
  - Requests per Second (RPS) 📈
  - Success/Failure Rates ✅/❌
  - Proxy Usage and Removal 🔄
  - PDF Download Count ⬇️
  - Estimated Time Remaining (ETR) ⏱️
- **Modular Design:** Well-structured code for easy maintenance and extension.

## 🛠️ Installation

1.  **Clone the repository:**

    ```bash
    git clone https://github.com/Anu-bhav/google-scholar-research
    cd google-scholar-research
    ```

2.  **Create and activate a virtual environment (recommended):**

    ```bash
    python3 -m venv venv
    source venv/bin/activate  # On Windows: venv\Scripts\activate
    ```

3.  **Install dependencies:**

    ```bash
    pip install -r requirements.txt
    ```

    Or install them individually:

    ```bash
    pip install aiohttp aiosqlite networkx pandas colorama fake-useragent parsel free-proxy tqdm
    ```

## 🚀 Usage

Run the scraper from the command line:

```bash
python google_scholar_research_tool.py "<search query>" [options]
```

**Available Options:**

| Option             | Short | Description                                                                           |         Default          |
| :----------------- | :---: | :------------------------------------------------------------------------------------ | :----------------------: |
| `<search query>`   |       | The main search query (keywords). Required unless `--author_profile` is used.         |                          |
| `--authors`        | `-a`  | Search for publications by specific author(s).                                        |          `None`          |
| `--publication`    | `-p`  | Search within a specific publication.                                                 |          `None`          |
| `--year_low`       | `-l`  | Lower bound of the publication year range.                                            |          `None`          |
| `--year_high`      | `-u`  | Upper bound of the publication year range.                                            |          `None`          |
| `--num_results`    | `-n`  | Maximum number of results to retrieve.                                                |           `10`           |
| `--output`         | `-o`  | Output file name (CSV or JSON).                                                       |      `results.csv`       |
| `--json`           |       | Output results in JSON format instead of CSV.                                         |         `False`          |
| `--pdf_dir`        |       | Directory to save downloaded PDFs.                                                    |          `pdfs`          |
| `--max_depth`      |       | Maximum recursion depth for citation network scraping.                                |           `3`            |
| `--graph_file`     |       | File name to save the citation network graph (GraphML format).                        | `citation_graph.graphml` |
| `--phrase`         |       | Search for an exact phrase.                                                           |          `None`          |
| `--exclude`        |       | Exclude keywords (comma-separated).                                                   |          `None`          |
| `--title`          |       | Search within the title.                                                              |          `None`          |
| `--author`         |       | Search within the author field.                                                       |          `None`          |
| `--source`         |       | Search within the source (publication).                                               |          `None`          |
| `--min_citations`  |       | Filter results: only include those with at least this many citations.                 |          `None`          |
| `--author_profile` |       | Scrape an author's profile using their Google Scholar ID.                             |          `None`          |
| `--recursive`      |       | Recursively scrape publications on an author's profile (requires `--author_profile`). |         `False`          |

**Examples:**

- Basic keyword search:

  ```bash
  python google_scholar_research_tool.py "machine learning"
  ```

  - Scrape author profile:

  ```bash
   python google_scholar_research_tool.py --author_profile "Yoshua Bengio" --output "yoshua_bengio.json" --json
  ```

- Search with author and year range, output to JSON:

  ```bash
  python google_scholar_research_tool.py "deep learning" -a "Yoshua Bengio" -l 2020 --json -o bengio_dl_2020.json
  ```

- Search with phrase, exclusion, and title constraints:

  ```bash
  python google_scholar_research_tool.py --phrase "generative adversarial networks" --exclude "image processing" --title "GANs in healthcare" -n 50
  ```

- Scrape author profile recursively and visualize graph with circular layout:

  ```bash
  python google_scholar_research_tool.py --author_profile "Yoshua Bengio" --recursive --graph_layout circular --graph_file bengio_citation_circular.graphml
  ```

  - Visualize citation graph with centrality filter (showing only papers with in-degree centrality >= 0.01):

  ```bash
  python google_scholar_research_tool.py "climate change" --graph_file climate_graph_filtered.graphml --centrality_filter 0.01
  ```

  - Run with INFO logging level (less verbose than DEBUG):

  ```bash
  python google_scholar_research_tool.py "renewable energy" --log_level INFO
  ```

  **Section 5: Important Considerations, License, Acknowledgements, Contributing, and Disclaimer**

## ⚠️ Important Considerations

- **Terms of Service:** Scraping Google Scholar may violate their Terms of Service. Use this tool responsibly and ethically. Google may block your IP address if you scrape too aggressively.
- **CAPTCHA:** Google Scholar uses CAPTCHAs. This scraper has basic detection, but bypassing them reliably is difficult. Expect to encounter CAPTCHAs, especially with frequent or large-scale scraping.
- **Proxies:** This tool uses _free_ proxies, which are often unreliable. For production use, _strongly_ consider using a reputable paid proxy service. **Note that the tool now includes proxy performance monitoring to better manage and select proxies, but the inherent limitations of free proxies still apply.**
- **Rate Limiting:** The scraper includes delays to be respectful, but you may need to adjust the timing (`--min_delay`, `--max_delay` - _not yet implemented as CLI options, but present in code_) based on your usage.

## 📜 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgements

- [aiohttp](https://docs.aiohttp.org/): Asynchronous HTTP client.
- [aiosqlite](https://aiosqlite.omnilib.dev/): Asynchronous SQLite wrapper.
- [parsel](https://parsel.readthedocs.io/): HTML/XML parsing library.
- [networkx](https://networkx.org/): Library for creating and manipulating graphs.
- [tqdm](https://tqdm.github.io/): Progress bar library.
- [fake-useragent](https://github.com/fake-useragent/fake-useragent): Generates random user agents.
- [free-proxy](https://github.com/howuku/free-proxy): For fetching free proxies.
- [Unpaywall](https://unpaywall.org/): For locating Open Access versions.

## 🤝 Contributing

Contributions are welcome! Please submit issues and pull requests. Follow the [black](https://github.com/psf/black) code style.

---

**Disclaimer:** This tool is for educational and research purposes. The author is not responsible for misuse. Always respect website terms of service and copyright laws.
