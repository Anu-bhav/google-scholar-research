# scholar_scraper.py
import argparse
import asyncio
import logging
import os

import pandas as pd
from data_handler import DataHandler
from exceptions import NoProxiesAvailable
from fetcher import Fetcher
from graph_builder import GraphBuilder
from proxy_manager import ProxyManager
from tqdm import tqdm


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

    args = parser.parse_args()

    if not args.query and not args.author_profile:
        parser.error("Either a query or --author_profile must be provided.")

    proxy_manager = ProxyManager()
    fetcher = Fetcher(proxy_manager=proxy_manager)
    data_handler = DataHandler()
    graph_builder = GraphBuilder()

    await data_handler.create_table()
    os.makedirs(args.pdf_dir, exist_ok=True)

    try:
        await proxy_manager.get_working_proxies()
    except NoProxiesAvailable:
        logging.error("No working proxies. Exiting.")
        return

    if args.author_profile:
        author_data = await fetcher.fetch_author_profile(args.author_profile)
        if author_data:
            if args.json:
                data_handler.save_to_json(author_data, args.output)
            else:  # Save author to csv if not json.
                df = pd.DataFrame([author_data])
                df.to_csv(args.output, index=False)
            print(f"Author profile data saved to {args.output}")

            if args.recursive:
                pass  # TODO: implement fetch details and recursive scraping.
                # for publication in author_data['publications']:
                # result = await fetcher.fetch_page(publication["link"]) # Implement fetch page details.

        else:
            print(f"Failed to fetch author profile for ID: {args.author_profile}")

    else:
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
            # Pass new arguments
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
            data_handler.save_to_json(results, args.output)
        else:
            data_handler.save_to_csv(results, args.output)
        logging.info(f"Successfully scraped and saved {len(results)} results in {args.output}")

        print(f"Citation graph: {graph_builder.graph.number_of_nodes()} nodes, {graph_builder.graph.number_of_edges()} edges")
        graph_builder.save_graph(args.graph_file)
        print(f"Citation graph saved to {args.graph_file}")
    await fetcher.close()


if __name__ == "__main__":
    logging.basicConfig(
        format="%(asctime)s | %(levelname)s | %(filename)s:%(lineno)d | %(funcName)s | %(message)s",
        level=logging.DEBUG,
    )
    asyncio.run(main())
