# google_scholar_research_tool.py
import argparse
import asyncio
import logging
import os
import random

import pandas as pd
from tqdm import tqdm

from .data_handler import DataHandler
from .exceptions import NoProxiesAvailable
from .fetcher import Fetcher
from .graph_builder import GraphBuilder
from .proxy_manager import NoProxiesAvailable, ProxyManager


async def main():
    parser = argparse.ArgumentParser(description="Scrape Google Scholar search results.")
    parser.add_argument("query", help="The search query.", nargs="?")  # Make query optional
    parser.add_argument("-a", "--authors", help="Search by author(s).", default=None)
    parser.add_argument("-p", "--publication", help="Search by publication.", default=None)
    parser.add_argument("-l", "--year_low", type=int, help="Lower bound of year range.", default=None)
    parser.add_argument("-u", "--year_high", type=int, help="Upper bound of year range.", default=None)
    parser.add_argument("-n", "--num_results", type=int, default=10, help="Max number of results.")
    parser.add_argument("-o", "--output", default="results.csv", help="Output file (CSV or JSON).")
    parser.add_argument("--json", action="store_true", help="Output in JSON format.")
    parser.add_argument("--pdf_dir", default="pdfs", help="Directory for PDFs.")
    parser.add_argument("--max_depth", type=int, default=3, help="Max citation depth.")
    parser.add_argument("--graph_file", default="citation_graph.graphml", help="Citation graph filename.")
    parser.add_argument(
        "--log_level", default="DEBUG", choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"], help="Logging level."
    )  # Added log level argument

    # --- Advanced Search Options ---
    parser.add_argument("--phrase", help="Search for an exact phrase.", default=None)
    parser.add_argument("--exclude", help="Exclude keywords (comma-separated).", default=None)
    parser.add_argument("--title", help="Search within the title.", default=None)
    parser.add_argument("--author", help="Search within the author field.", default=None)
    parser.add_argument("--source", help="Search within the source (publication).", default=None)
    parser.add_argument("--min_citations", type=int, help="Minimum number of citations.", default=None)
    parser.add_argument("--author_profile", type=str, help="Scrape an author's profile by their ID.")  # Added author profile
    parser.add_argument(
        "--recursive", action="store_true", help="Recursively scrape author's publications."
    )  # Added recursive flag
    parser.add_argument(
        "--graph_layout", default="spring", choices=["spring", "circular", "kamada_kawai"], help="Graph visualization layout."
    )  # Added graph layout option
    parser.add_argument(
        "--centrality_filter", type=float, default=None, help="Filter graph visualization by centrality (>=)."
    )  # Centrality filter

    args = parser.parse_args()

    # --- Input Validation ---
    if not args.query and not args.author_profile:
        parser.error("Error: Either a query or --author_profile must be provided.")
    if args.num_results <= 0:
        parser.error("Error: --num_results must be a positive integer.")
    if args.max_depth < 0:
        parser.error("Error: --max_depth cannot be negative.")
    if args.year_low is not None and not (1000 <= args.year_low <= 2100):
        parser.error("Error: --year_low must be a valid year (1000-2100).")
    if args.year_high is not None and not (1000 <= args.year_high <= 2100):
        parser.error("Error: --year_high must be a valid year (1000-2100).")
    if args.centrality_filter is not None and args.centrality_filter < 0:
        parser.error("Error: --centrality_filter must be a non-negative value.")

    # --- Logging Configuration ---
    logging.basicConfig(
        format="%(asctime)s | %(levelname)s | %(filename)s:%(lineno)d | %(funcName)s | %(message)s",
        level=args.log_level.upper(),  # Set log level from argument
    )

    proxy_manager = ProxyManager()
    fetcher = Fetcher(proxy_manager=proxy_manager)
    data_handler = DataHandler()
    graph_builder = GraphBuilder()

    await data_handler.create_table()
    os.makedirs(args.pdf_dir, exist_ok=True)

    try:  # Top-level error handling
        try:
            await proxy_manager.get_working_proxies()
        except NoProxiesAvailable:
            logging.error("No working proxies available. Exiting.")
            return

        if args.author_profile:
            author_data = await fetcher.fetch_author_profile(args.author_profile)
            if author_data:
                if args.json:
                    data_handler.save_to_json(author_data, args.output)
                else:  # Save author to csv if not json.
                    df = pd.DataFrame([author_data])
                    try:  # Output file error handling
                        df.to_csv(args.output, index=False)
                    except IOError as e:
                        logging.error(f"Error saving to CSV file '{args.output}': {e}", exc_info=True)
                        print(f"Error saving to CSV file. Check logs for details.")
                        return
                print(f"Author profile data saved to {args.output}")

                if args.recursive:
                    recursive_results = []
                    print("Recursively scraping author's publications...")
                    for pub in tqdm(author_data["publications"], desc="Fetching Publication Details", unit="pub"):
                        publication_detail = await fetcher.scrape_publication_details(pub["link"])  # Use new fetcher method
                        if publication_detail:
                            recursive_results.extend(publication_detail)  # Extend with list of results
                        await asyncio.sleep(random.uniform(1, 2))  # Polite delay

                    if recursive_results:
                        print(f"Recursively scraped {len(recursive_results)} publication details.")
                        if args.json:
                            try:  # Output file error handling for recursive results
                                data_handler.save_to_json(recursive_results, "recursive_" + args.output)  # Save to separate file
                            except IOError as e:
                                logging.error(
                                    f"Error saving recursive results to JSON file 'recursive_{args.output}': {e}", exc_info=True
                                )
                                print(f"Error saving recursive results to JSON file. Check logs.")
                        else:
                            df_recursive = pd.DataFrame(recursive_results)
                            try:  # Output file error handling for recursive results CSV
                                df_recursive.to_csv("recursive_" + args.output, index=False)  # Save to separate CSV
                            except IOError as e:
                                logging.error(
                                    f"Error saving recursive results to CSV file 'recursive_{args.output}': {e}", exc_info=True
                                )
                                print(f"Error saving recursive results to CSV file. Check logs.")
                        print(f"Recursive publication details saved to recursive_{args.output}")
                    else:
                        print("No publication details found during recursive scraping.")

        else:  # Main scraping logic for search queries
            results = await fetcher.scrape(
                args.query,
                args.authors,
                args.publication,
                args.year_low,
                args.year_high,
                args.num_results,
                args.pdf_dir,
                args.max_depth,
                graph_builder,
                data_handler,
                # Pass advanced search parameters
                phrase=args.phrase,
                exclude=args.exclude,
                title=args.title,
                author=args.author,
                source=args.source,
            )

            # --- Data Filtering (Add this section) ---
            if args.min_citations:
                results = [result for result in results if result["cited_by_count"] >= args.min_citations]

            if args.json:
                try:  # Output file error handling
                    data_handler.save_to_json(results, args.output)
                except IOError as e:
                    logging.error(f"Error saving to JSON file '{args.output}': {e}", exc_info=True)
                    print(f"Error saving to JSON file. Check logs for details.")
                    return
            else:
                try:  # Output file error handling
                    data_handler.save_to_csv(results, args.output)
                except IOError as e:
                    logging.error(f"Error saving to CSV file '{args.output}': {e}", exc_info=True)
                    print(f"Error saving to CSV file. Check logs for details.")
                    return
            logging.info(f"Successfully scraped and saved {len(results)} results in {args.output}")

            print(f"Citation graph: {graph_builder.graph.number_of_nodes()} nodes, {graph_builder.graph.number_of_edges()} edges")
            graph_builder.save_graph(args.graph_file)
            print(f"Citation graph saved to {args.graph_file}")

            graph_builder.generate_default_visualizations(
                base_filename=args.graph_file.replace(".graphml", "")
            )  # Generate default visualizations
            print(f"Citation graph visualizations saved to {graph_builder.output_folder} folder")

    except Exception as e:  # Top-level exception handler for any unhandled errors
        logging.critical(f"Unhandled exception in main(): {e}", exc_info=True)  # Log critical error with traceback
        print(
            f"A critical error occurred: {type(e).__name__} - {e}. Please check the logs for more details."
        )  # User-friendly error message

    finally:
        await fetcher.close()
        proxy_manager.log_proxy_performance()
        logging.info("--- Scraping process finished ---")  # End process log message


if __name__ == "__main__":
    asyncio.run(main())
