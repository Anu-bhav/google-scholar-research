# scholar_scraper/scholar_scraper/main.py
import argparse
import asyncio
import logging
import os
import re
import sys

from colorama import Back, Fore, Style, init

from .data_handler import DataHandler
from .exceptions import NoProxiesAvailable
from .fetcher import Fetcher
from .graph_builder import GraphBuilder  # import GraphBuilder
from .parser import Parser
from .proxy_manager import ProxyManager
from .query_builder import QueryBuilder

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(filename)s:%(lineno)d | %(funcName)s | %(message)s",
    level=logging.DEBUG)


def usage():
    """Prints a comprehensive, colorized usage guide to the console."""
    init(autoreset=True)

    parser = argparse.ArgumentParser(
        description=f"{Fore.CYAN}ScholarScraper: {Fore.WHITE}A Python tool for efficient and comprehensive scraping of Google Scholar.",
        formatter_class=argparse.RawTextHelpFormatter,
        epilog=(  # Add an epilog for extra information
            f"{Fore.LIGHTBLACK_EX}Examples:\n"
            f'  {Fore.MAGENTA}python -m scholar_scraper.main "machine learning"{Style.RESET_ALL}  (Basic search)\n'
            f'  {Fore.MAGENTA}python -m scholar_scraper.main "deep learning" -a "Yoshua Bengio" -l 2020 --json -o results.json{Style.RESET_ALL}  (Advanced search)\n'
            f'  {Fore.MAGENTA}python -m scholar_scraper.main "quantum computing" --pdf_dir qc_pdfs -n 50{Style.RESET_ALL}  (Download PDFs)\n\n'
            f"{Fore.LIGHTBLACK_EX}Notes:\n"
            f"  * {Fore.CYAN}Always run the script using{Style.RESET_ALL} {Fore.MAGENTA}python -m scholar_scraper.main{Style.RESET_ALL} {Fore.CYAN}to ensure correct package imports.{Style.RESET_ALL}\n"
            f"  * {Fore.CYAN}Free proxies are used, which may be unreliable. Consider a paid proxy service for production use.{Style.RESET_ALL}\n"
            f"  * {Fore.CYAN}Be respectful of Google Scholar's Terms of Service and avoid excessive scraping.{Style.RESET_ALL}"
        ),
    )

    # --- Positional Arguments ---
    positional_group = parser.add_argument_group(f"{Fore.GREEN}Positional Arguments{Style.RESET_ALL}")
    positional_group.add_argument(
        "query",
        help=f"{Fore.YELLOW}The search query (REQUIRED).{Style.RESET_ALL}  Enclose in quotes for multi-word queries.",
    )

    # --- Optional Arguments ---
    optional_group = parser.add_argument_group(f"{Fore.GREEN}Optional Arguments{Style.RESET_ALL}")
    optional_group.add_argument(
        "-a",
        "--authors",
        help=f'{Fore.YELLOW}Search for publications by specific author(s).{Style.RESET_ALL} Separate multiple authors with commas (e.g., "Yann LeCun, Yoshua Bengio").',
        default=None,
    )
    optional_group.add_argument(
        "-p",
        "--publication",
        help=f'{Fore.YELLOW}Search within a specific publication (e.g., "Nature", "Science").{Style.RESET_ALL}',
        default=None,
    )
    optional_group.add_argument(
        "-l",
        "--year_low",
        type=int,
        help=f"{Fore.YELLOW}The lower bound of the publication year range (inclusive).{Style.RESET_ALL}",
        default=None,
    )
    optional_group.add_argument(
        "-u",
        "--year_high",
        type=int,
        help=f"{Fore.YELLOW}The upper bound of the publication year range (inclusive).{Style.RESET_ALL}",
        default=None,
    )
    optional_group.add_argument(
        "-n",
        "--num_results",
        type=int,
        default=10,
        help=f"{Fore.YELLOW}The maximum number of results to retrieve.{Style.RESET_ALL} (default: 10)",
    )
    optional_group.add_argument(
        "-o",
        "--output",
        default="results.csv",
        help=f"{Fore.YELLOW}Output file name.{Style.RESET_ALL} (default: results.csv).  File extension determines format (CSV or JSON).",
    )
    optional_group.add_argument(
        "--json",
        action="store_true",
        help=f"{Fore.YELLOW}Output results in JSON format.{Style.RESET_ALL} (default: CSV).  Overrides file extension if both are provided.",
    )
    optional_group.add_argument(
        "--pdf_dir",
        default="pdfs",
        help=f"{Fore.YELLOW}Directory to save downloaded PDFs.{Style.RESET_ALL} (default: pdfs).  The directory will be created if it doesn't exist.",
    )
    optional_group.add_argument(
        "--max_depth",
        type=int,
        default=3,
        help=f"{Fore.YELLOW}Maximum recursion depth for citation network scraping.{Style.RESET_ALL} (default: 3).  Higher values may result in more comprehensive citation networks but also more requests.",
    )

    # --- Output the formatted help ---
    print(parser.format_help())


async def main():
    # Argument parsing:  Define arguments ONLY ONCE, here in main().
    parser = argparse.ArgumentParser(description="Scrape Google Scholar search results.")
    parser.add_argument("query", help="The search query.")
    parser.add_argument("-a", "--authors", help="Search by author(s).", default=None)
    parser.add_argument("-p", "--publication", help="Search by publication.", default=None)
    parser.add_argument("-l", "--year_low", type=int, help="The lower bound of the year range.", default=None)
    parser.add_argument("-u", "--year_high", type=int, help="The upper bound of the year range.", default=None)
    parser.add_argument("-n", "--num_results", type=int, default=10, help="The maximum number of results to retrieve.")
    parser.add_argument("-o", "--output", default="results.csv", help="Output file name (CSV or JSON).")
    parser.add_argument("--json", action="store_true", help="Output in JSON format (default is CSV).")
    parser.add_argument("--pdf_dir", default="pdfs", help="Directory to save downloaded PDFs.")
    parser.add_argument("--max_depth", type=int, default=3, help="Maximum recursion depth for citation network scraping.")
    # Let argparse handle -h/--help automatically:
    args = parser.parse_args()  # Parse arguments ONLY ONCE, here.

    # Removed the if args.help check, argparse will exit.

    query_builder = QueryBuilder()
    proxy_manager = ProxyManager()
    try:
        await proxy_manager.get_working_proxies()  # Ensure we have proxies before starting
    except NoProxiesAvailable:
        logging.error("No working proxies available. Exiting.")
        return
    fetcher = Fetcher(proxy_manager=proxy_manager)
    parser = Parser()
    data_handler = DataHandler()
    # Create PDF directory if it doesn't exist
    os.makedirs(args.pdf_dir, exist_ok=True)

    all_results = []
    start_index = 0

    graph_builder = GraphBuilder()  # Initialize GraphBuilder

    while len(all_results) < args.num_results:
        url = query_builder.build_url(
            args.query,
            start=start_index,
            authors=args.authors,
            publication=args.publication,
            year_low=args.year_low,
            year_high=args.year_high,
        )

        # Check if result exists in the database
        if data_handler.result_exists(url):
            logging.info(f"Skipping already scraped URL: {url}")
            start_index += 10  # increment and skip.
            continue

        html_content = await fetcher.fetch_page(url)
        if html_content:
            parsed_results_with_items = list(
                zip(parser.parse_results(html_content, True), parser.parse_raw_items(html_content))
            )  # using zip to associate item with result.
            results = [result_item[0] for result_item in parsed_results_with_items]  # get result
            raw_items = [result_item[1] for result_item in parsed_results_with_items]  # get raw item

            if not results:
                logging.info("No more results found.")
                break  # Exit loop if no more results

            for item, result in zip(raw_items, results):  # using zip to associate item with result.
                # --- PDF Handling ---
                pdf_url = None  # Initialize pdf_url here
                if result.get("doi"):
                    pdf_url = await fetcher.scrape_pdf_link(result["doi"])

                # Fallback to extract_pdf_url if DOI-based method fails
                if not pdf_url:
                    # Call extract_pdf_url *only* if scrape_pdf_link failed
                    extracted_url = parser.extract_pdf_url(item)  # Pass the 'item'
                    if extracted_url:
                        # Handle relative URLs
                        if extracted_url.startswith("/"):
                            pdf_url = "https://scholar.google.com" + extracted_url
                        else:
                            pdf_url = extracted_url

                if pdf_url:
                    result["pdf_url"] = pdf_url
                    # Sanitize the title for use as a filename
                    safe_title = re.sub(r'[\\/*?:"<>|]', "", result["title"])
                    pdf_filename = os.path.join(
                        args.pdf_dir, f"{safe_title}_{result.get('publication_info', {}).get('year', 'unknown')}.pdf"
                    )
                    if await fetcher.download_pdf(pdf_url, pdf_filename):
                        result["pdf_path"] = pdf_filename

                # --- Incremental Scraping ---
                data_handler.insert_result(result)  # Insert *after* potential PDF download

                # --- Citation Network---
                graph_builder.add_citation(
                    result["title"], result["article_url"], result.get("cited_by_url")
                )  # add to citation network
                if result.get("cited_by_url"):
                    await fetcher.fetch_cited_by_page(
                        result["cited_by_url"], proxy_manager, 1, args.max_depth, graph_builder
                    )  # Start recursion

            all_results.extend(results)
            next_page = parser.find_next_page(html_content)
            if next_page:
                start_index += 10
            else:
                break
        else:
            logging.error("Failed to fetch results.")
            break

    # Trim results to the desired number
    all_results = all_results[: args.num_results]

    if args.json:
        data_handler.save_to_json(all_results, args.output)
        logging.info(f"Successfully scraped and saved {len(all_results)} results in {args.output}")
    else:
        data_handler.save_to_csv(all_results, args.output)
        logging.info(f"Successfully scraped and saved {len(all_results)} results in {args.output}")

    # Graph output
    print(f"Citation graph: {graph_builder.graph.number_of_nodes()} nodes, {graph_builder.graph.number_of_edges()} edges")


if __name__ == "__main__":
    asyncio.run(main())
