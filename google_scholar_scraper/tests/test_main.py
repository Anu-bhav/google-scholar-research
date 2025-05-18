import argparse
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# To avoid naming conflict if main.py is also imported directly for other reasons
from google_scholar_scraper.main import main as async_main_entry
from google_scholar_scraper.proxy_manager import NoProxiesAvailable


@pytest.mark.asyncio
async def test_main_basic_query_csv_output():
    """Test the main function with a basic query and CSV output."""
    # 1. Simulate command line arguments
    test_argv = [
        "main.py",
        "test query",
        "--num_results",
        "7",
        "--output",
        "test_output.csv",
        "--pdf_dir",
        "test_pdfs",
        "--graph_file",
        "test_graph.graphml",
        "--log_level",
        "ERROR",  # Use a non-default to check arg passing
    ]

    # 2. Mock argparse
    # Create a mock Namespace object that parse_args would return
    mock_args = argparse.Namespace(
        query="test query",
        authors=None,
        publication=None,
        year_low=None,
        year_high=None,
        num_results=7,
        output="test_output.csv",
        json=False,
        pdf_dir="test_pdfs",
        max_depth=3,  # Default
        graph_file="test_graph.graphml",
        log_level="ERROR",
        phrase=None,
        exclude=None,
        title=None,
        author=None,  # This is different from --authors
        source=None,
        min_citations=None,
        author_profile=None,
        recursive=False,
        graph_layout="spring",  # Default
        centrality_filter=None,  # Default
    )

    # 3. Patch all major components and functions used by main
    with (
        patch("sys.argv", test_argv),
        patch("argparse.ArgumentParser.parse_args", return_value=mock_args) as mock_parse_args,
        patch("google_scholar_scraper.main.ProxyManager") as MockProxyManager,
        patch("google_scholar_scraper.main.Fetcher") as MockFetcher,
        patch("google_scholar_scraper.main.DataHandler") as MockDataHandler,
        patch("google_scholar_scraper.main.GraphBuilder") as MockGraphBuilder,
        patch("google_scholar_scraper.main.os.makedirs") as mock_os_makedirs,
        patch("google_scholar_scraper.main.logging.basicConfig") as mock_logging_config,
    ):
        # Configure instances returned by constructors
        mock_proxy_manager_instance = MockProxyManager.return_value
        mock_proxy_manager_instance.get_working_proxies = AsyncMock()  # Succeeds by default
        mock_proxy_manager_instance.log_proxy_performance = MagicMock()

        mock_fetcher_instance = MockFetcher.return_value
        mock_fetcher_instance.scrape = AsyncMock(return_value=[{"title": "Result 1"}])  # Dummy results
        mock_fetcher_instance.close = AsyncMock()

        mock_data_handler_instance = MockDataHandler.return_value
        mock_data_handler_instance.create_table = AsyncMock()
        mock_data_handler_instance.save_to_csv = MagicMock()
        mock_data_handler_instance.save_to_json = MagicMock()  # For completeness

        mock_graph_builder_instance = MockGraphBuilder.return_value
        mock_graph_builder_instance.graph = MagicMock()  # Mock the graph attribute
        mock_graph_builder_instance.graph.number_of_nodes.return_value = 1
        mock_graph_builder_instance.graph.number_of_edges.return_value = 0
        mock_graph_builder_instance.save_graph = MagicMock()
        mock_graph_builder_instance.generate_default_visualizations = MagicMock()

        # 4. Run the main function
        await async_main_entry()

        # 5. Assertions
        mock_parse_args.assert_called_once()

        MockProxyManager.assert_called_once()
        mock_proxy_manager_instance.get_working_proxies.assert_called_once()

        MockFetcher.assert_called_once_with(proxy_manager=mock_proxy_manager_instance)

        MockDataHandler.assert_called_once()
        mock_data_handler_instance.create_table.assert_called_once()

        MockGraphBuilder.assert_called_once()

        mock_os_makedirs.assert_called_once_with(mock_args.pdf_dir, exist_ok=True)
        mock_logging_config.assert_called_once()
        # Check if log level was set (more complex, check call_args of basicConfig)
        assert mock_logging_config.call_args.kwargs["level"] == "ERROR"

        mock_fetcher_instance.scrape.assert_called_once_with(
            mock_args.query,
            mock_args.authors,
            mock_args.publication,
            mock_args.year_low,
            mock_args.year_high,
            mock_args.num_results,
            mock_args.pdf_dir,
            mock_args.max_depth,
            mock_graph_builder_instance,
            mock_data_handler_instance,
            phrase=mock_args.phrase,
            exclude=mock_args.exclude,
            title=mock_args.title,
            author=mock_args.author,
            source=mock_args.source,
        )

        mock_data_handler_instance.save_to_csv.assert_called_once_with(
            mock_fetcher_instance.scrape.return_value,  # results
            mock_args.output,
        )
        mock_data_handler_instance.save_to_json.assert_not_called()

        mock_graph_builder_instance.save_graph.assert_called_once_with(mock_args.graph_file)
        mock_graph_builder_instance.generate_default_visualizations.assert_called_once_with(
            base_filename=mock_args.graph_file.replace(".graphml", "")
        )

        mock_fetcher_instance.close.assert_called_once()
        mock_proxy_manager_instance.log_proxy_performance.assert_called_once()


@pytest.mark.asyncio
async def test_main_basic_query_json_output():
    """Test the main function with a basic query and JSON output."""
    test_argv = [
        "main.py",
        "json query",
        "--num_results",
        "3",
        "--output",
        "test_output.json",
        "--json",  # Specify JSON output
        "--pdf_dir",
        "test_pdfs_json",
        "--graph_file",
        "test_graph_json.graphml",
        "--log_level",
        "INFO",
    ]

    mock_args = argparse.Namespace(
        query="json query",
        authors=None,
        publication=None,
        year_low=None,
        year_high=None,
        num_results=3,
        output="test_output.json",
        json=True,  # JSON flag is true
        pdf_dir="test_pdfs_json",
        max_depth=3,
        graph_file="test_graph_json.graphml",
        log_level="INFO",
        phrase=None,
        exclude=None,
        title=None,
        author=None,
        source=None,
        min_citations=None,
        author_profile=None,
        recursive=False,
        graph_layout="spring",
        centrality_filter=None,
    )

    with (
        patch("sys.argv", test_argv),
        patch("argparse.ArgumentParser.parse_args", return_value=mock_args) as mock_parse_args,
        patch("google_scholar_scraper.main.ProxyManager") as MockProxyManager,
        patch("google_scholar_scraper.main.Fetcher") as MockFetcher,
        patch("google_scholar_scraper.main.DataHandler") as MockDataHandler,
        patch("google_scholar_scraper.main.GraphBuilder") as MockGraphBuilder,
        patch("google_scholar_scraper.main.os.makedirs") as mock_os_makedirs,
        patch("google_scholar_scraper.main.logging.basicConfig") as mock_logging_config,
    ):
        mock_proxy_manager_instance = MockProxyManager.return_value
        mock_proxy_manager_instance.get_working_proxies = AsyncMock()
        mock_proxy_manager_instance.log_proxy_performance = MagicMock()

        mock_fetcher_instance = MockFetcher.return_value
        mock_fetcher_instance.scrape = AsyncMock(return_value=[{"title": "JSON Result"}])
        mock_fetcher_instance.close = AsyncMock()

        mock_data_handler_instance = MockDataHandler.return_value
        mock_data_handler_instance.create_table = AsyncMock()
        mock_data_handler_instance.save_to_csv = MagicMock()
        mock_data_handler_instance.save_to_json = MagicMock()

        mock_graph_builder_instance = MockGraphBuilder.return_value
        mock_graph_builder_instance.graph = MagicMock()
        mock_graph_builder_instance.graph.number_of_nodes.return_value = 1
        mock_graph_builder_instance.graph.number_of_edges.return_value = 0
        mock_graph_builder_instance.save_graph = MagicMock()
        mock_graph_builder_instance.generate_default_visualizations = MagicMock()

        await async_main_entry()

        mock_parse_args.assert_called_once()
        MockProxyManager.assert_called_once()
        mock_proxy_manager_instance.get_working_proxies.assert_called_once()
        MockFetcher.assert_called_once_with(proxy_manager=mock_proxy_manager_instance)
        MockDataHandler.assert_called_once()
        mock_data_handler_instance.create_table.assert_called_once()
        MockGraphBuilder.assert_called_once()
        mock_os_makedirs.assert_called_once_with(mock_args.pdf_dir, exist_ok=True)
        assert mock_logging_config.call_args.kwargs["level"] == "INFO"

        mock_fetcher_instance.scrape.assert_called_once_with(
            mock_args.query,
            mock_args.authors,
            mock_args.publication,
            mock_args.year_low,
            mock_args.year_high,
            mock_args.num_results,
            mock_args.pdf_dir,
            mock_args.max_depth,
            mock_graph_builder_instance,
            mock_data_handler_instance,
            phrase=mock_args.phrase,
            exclude=mock_args.exclude,
            title=mock_args.title,
            author=mock_args.author,
            source=mock_args.source,
        )

        # Assert JSON save was called and CSV was not
        mock_data_handler_instance.save_to_json.assert_called_once_with(
            mock_fetcher_instance.scrape.return_value,  # results
            mock_args.output,
        )
        mock_data_handler_instance.save_to_csv.assert_not_called()

        mock_graph_builder_instance.save_graph.assert_called_once_with(mock_args.graph_file)
        mock_graph_builder_instance.generate_default_visualizations.assert_called_once_with(
            base_filename=mock_args.graph_file.replace(".graphml", "")
        )

        mock_fetcher_instance.close.assert_called_once()
        mock_proxy_manager_instance.log_proxy_performance.assert_called_once()


@pytest.mark.asyncio
async def test_main_author_profile_scraping_json_output():
    """Test main function for author profile scraping with JSON output."""
    test_argv = [
        "main.py",
        "--author_profile",
        "test_author_id",
        "--output",
        "author_output.json",
        "--json",
        "--pdf_dir",
        "author_pdfs",  # Still need pdf_dir for os.makedirs
        "--log_level",
        "DEBUG",
    ]

    mock_args = argparse.Namespace(
        query=None,  # No query when author_profile is set
        authors=None,
        publication=None,
        year_low=None,
        year_high=None,
        num_results=10,  # Default, not used for author profile directly
        output="author_output.json",
        json=True,
        pdf_dir="author_pdfs",
        max_depth=3,  # Default, not used for non-recursive author profile
        graph_file="citation_graph.graphml",  # Default, not used here
        log_level="DEBUG",
        phrase=None,
        exclude=None,
        title=None,
        author=None,
        source=None,
        min_citations=None,
        author_profile="test_author_id",
        recursive=False,  # Not recursive for this test
        graph_layout="spring",  # Default, not used here
        centrality_filter=None,  # Default, not used here
    )

    dummy_author_data = {"name": "Test Author", "publications": [{"title": "Pub1"}]}

    with (
        patch("sys.argv", test_argv),
        patch("argparse.ArgumentParser.parse_args", return_value=mock_args) as mock_parse_args,
        patch("google_scholar_scraper.main.ProxyManager") as MockProxyManager,
        patch("google_scholar_scraper.main.Fetcher") as MockFetcher,
        patch("google_scholar_scraper.main.DataHandler") as MockDataHandler,
        patch("google_scholar_scraper.main.GraphBuilder") as MockGraphBuilder,
        patch("google_scholar_scraper.main.os.makedirs") as mock_os_makedirs,
        patch("google_scholar_scraper.main.logging.basicConfig") as mock_logging_config,
        patch("google_scholar_scraper.main.pd.DataFrame") as MockDataFrame,
    ):  # For CSV path if json=False
        mock_proxy_manager_instance = MockProxyManager.return_value
        mock_proxy_manager_instance.get_working_proxies = AsyncMock()
        mock_proxy_manager_instance.log_proxy_performance = MagicMock()

        mock_fetcher_instance = MockFetcher.return_value
        mock_fetcher_instance.fetch_author_profile = AsyncMock(return_value=dummy_author_data)
        mock_fetcher_instance.scrape_publication_details = AsyncMock()  # Should not be called
        mock_fetcher_instance.scrape = AsyncMock()  # Should not be called
        mock_fetcher_instance.close = AsyncMock()

        mock_data_handler_instance = MockDataHandler.return_value
        mock_data_handler_instance.create_table = AsyncMock()
        mock_data_handler_instance.save_to_json = MagicMock()
        mock_data_handler_instance.save_to_csv = MagicMock()  # For pd.DataFrame().to_csv

        # GraphBuilder is instantiated but not used for graph saving/viz in this path
        mock_graph_builder_instance = MockGraphBuilder.return_value
        mock_graph_builder_instance.save_graph = MagicMock()
        mock_graph_builder_instance.generate_default_visualizations = MagicMock()

        await async_main_entry()

        mock_parse_args.assert_called_once()
        MockProxyManager.assert_called_once()
        mock_proxy_manager_instance.get_working_proxies.assert_called_once()
        MockFetcher.assert_called_once_with(proxy_manager=mock_proxy_manager_instance)
        MockDataHandler.assert_called_once()
        mock_data_handler_instance.create_table.assert_called_once()
        MockGraphBuilder.assert_called_once()  # Instantiated
        mock_os_makedirs.assert_called_once_with(mock_args.pdf_dir, exist_ok=True)
        assert mock_logging_config.call_args.kwargs["level"] == "DEBUG"

        mock_fetcher_instance.fetch_author_profile.assert_called_once_with(mock_args.author_profile)
        mock_fetcher_instance.scrape.assert_not_called()
        mock_fetcher_instance.scrape_publication_details.assert_not_called()

        mock_data_handler_instance.save_to_json.assert_called_once_with(dummy_author_data, mock_args.output)
        mock_data_handler_instance.save_to_csv.assert_not_called()
        MockDataFrame.assert_not_called()  # Should not be called if json=True

        # Graph operations should not be called for non-recursive author profile
        mock_graph_builder_instance.save_graph.assert_not_called()
        mock_graph_builder_instance.generate_default_visualizations.assert_not_called()

        mock_fetcher_instance.close.assert_called_once()
        mock_proxy_manager_instance.log_proxy_performance.assert_called_once()


@pytest.mark.asyncio
async def test_main_author_profile_recursive_scraping_json_output():
    """Test main function for recursive author profile scraping with JSON output."""
    test_argv = [
        "main.py",
        "--author_profile",
        "recursive_author_id",
        "--recursive",  # Recursive flag
        "--output",
        "recursive_author_output.json",
        "--json",
        "--pdf_dir",
        "recursive_pdfs",
        "--log_level",
        "INFO",
    ]

    mock_args = argparse.Namespace(
        query=None,
        authors=None,
        publication=None,
        year_low=None,
        year_high=None,
        num_results=10,
        output="recursive_author_output.json",
        json=True,
        pdf_dir="recursive_pdfs",
        max_depth=3,
        graph_file="citation_graph.graphml",
        log_level="INFO",
        phrase=None,
        exclude=None,
        title=None,
        author=None,
        source=None,
        min_citations=None,
        author_profile="recursive_author_id",
        recursive=True,  # Recursive is true
        graph_layout="spring",
        centrality_filter=None,
    )

    author_pubs = [{"title": "Pub1", "link": "link_to_pub1"}, {"title": "Pub2", "link": "link_to_pub2"}]
    dummy_author_data = {"name": "Recursive Author", "publications": author_pubs}
    dummy_pub1_details = [{"detail_title": "Detail Pub1"}]
    dummy_pub2_details = [{"detail_title": "Detail Pub2"}]

    # Configure side_effect for scrape_publication_details to return different details per call
    # This matches the number of publications in author_pubs
    scrape_details_side_effect = [dummy_pub1_details, dummy_pub2_details]

    with (
        patch("sys.argv", test_argv),
        patch("argparse.ArgumentParser.parse_args", return_value=mock_args) as mock_parse_args,
        patch("google_scholar_scraper.main.ProxyManager") as MockProxyManager,
        patch("google_scholar_scraper.main.Fetcher") as MockFetcher,
        patch("google_scholar_scraper.main.DataHandler") as MockDataHandler,
        patch("google_scholar_scraper.main.GraphBuilder") as MockGraphBuilder,
        patch("google_scholar_scraper.main.os.makedirs") as mock_os_makedirs,
        patch("google_scholar_scraper.main.logging.basicConfig") as mock_logging_config,
        patch("google_scholar_scraper.main.pd.DataFrame") as MockDataFrame,
        patch("google_scholar_scraper.main.asyncio.sleep", new_callable=AsyncMock) as mock_async_sleep,
        patch("google_scholar_scraper.main.tqdm", side_effect=lambda x, **kwargs: x) as mock_tqdm,
    ):  # Mock tqdm to pass through iterables
        mock_proxy_manager_instance = MockProxyManager.return_value
        mock_proxy_manager_instance.get_working_proxies = AsyncMock()
        mock_proxy_manager_instance.log_proxy_performance = MagicMock()

        mock_fetcher_instance = MockFetcher.return_value
        mock_fetcher_instance.fetch_author_profile = AsyncMock(return_value=dummy_author_data)
        mock_fetcher_instance.scrape_publication_details = AsyncMock(side_effect=scrape_details_side_effect)
        mock_fetcher_instance.scrape = AsyncMock()  # Should not be called
        mock_fetcher_instance.close = AsyncMock()

        mock_data_handler_instance = MockDataHandler.return_value
        mock_data_handler_instance.create_table = AsyncMock()
        mock_data_handler_instance.save_to_json = MagicMock()

        mock_graph_builder_instance = MockGraphBuilder.return_value  # Instantiated but not used

        await async_main_entry()

        mock_parse_args.assert_called_once()
        mock_proxy_manager_instance.get_working_proxies.assert_called_once()
        mock_fetcher_instance.fetch_author_profile.assert_called_once_with(mock_args.author_profile)

        # Check calls to scrape_publication_details
        assert mock_fetcher_instance.scrape_publication_details.call_count == len(author_pubs)
        mock_fetcher_instance.scrape_publication_details.assert_any_call(author_pubs[0]["link"])
        mock_fetcher_instance.scrape_publication_details.assert_any_call(author_pubs[1]["link"])

        # Check calls to save_to_json (once for author, once for recursive results)
        assert mock_data_handler_instance.save_to_json.call_count == 2
        expected_recursive_results = dummy_pub1_details + dummy_pub2_details

        # Check the first call (author profile)
        mock_data_handler_instance.save_to_json.assert_any_call(dummy_author_data, mock_args.output)
        # Check the second call (recursive results)
        mock_data_handler_instance.save_to_json.assert_any_call(expected_recursive_results, "recursive_" + mock_args.output)

        mock_fetcher_instance.scrape.assert_not_called()
        mock_graph_builder_instance.save_graph.assert_not_called()  # Graph ops not for author profile
        mock_graph_builder_instance.generate_default_visualizations.assert_not_called()

        assert mock_async_sleep.call_count == len(author_pubs)  # Polite delay called per pub

        mock_fetcher_instance.close.assert_called_once()
        mock_proxy_manager_instance.log_proxy_performance.assert_called_once()


# Test cases for input validation errors
validation_error_cases = [
    # (dict_of_args_to_set_on_mock_args, expected_error_message_substring)
    ({"query": None, "author_profile": None}, "Either a query or --author_profile must be provided"),
    ({"num_results": 0}, "--num_results must be a positive integer"),
    ({"num_results": -1}, "--num_results must be a positive integer"),
    ({"max_depth": -1}, "--max_depth cannot be negative"),
    ({"year_low": 900}, "--year_low must be a valid year"),
    ({"year_low": 2200}, "--year_low must be a valid year"),
    ({"year_high": 900}, "--year_high must be a valid year"),
    ({"year_high": 2200}, "--year_high must be a valid year"),
    ({"centrality_filter": -0.1}, "--centrality_filter must be a non-negative value"),
]


@pytest.mark.asyncio
@pytest.mark.parametrize("args_to_set, expected_error_substring", validation_error_cases)
async def test_main_input_validation_errors(args_to_set, expected_error_substring):
    """Test input validation errors in the main function."""
    test_argv = ["main.py", "some_default_query"]  # Basic argv, parse_args is mocked

    # Base mock_args, will be updated by args_to_set
    # Ensure one of query or author_profile is initially valid to avoid premature error
    # before the specific validation under test.
    base_mock_args = argparse.Namespace(
        query="default_query_for_validation",
        authors=None,
        publication=None,
        year_low=None,
        year_high=None,
        num_results=10,
        output="val_output.csv",
        json=False,
        pdf_dir="val_pdfs",
        max_depth=3,
        graph_file="val_graph.graphml",
        log_level="INFO",
        phrase=None,
        exclude=None,
        title=None,
        author=None,
        source=None,
        min_citations=None,
        author_profile=None,
        recursive=False,
        graph_layout="spring",
        centrality_filter=None,
    )

    # Update mock_args with the specific invalid values for this test case
    for key, value in args_to_set.items():
        setattr(base_mock_args, key, value)

    # Mock the ArgumentParser instance itself to control its 'error' method
    mock_parser_instance = MagicMock(spec=argparse.ArgumentParser)
    # When parser.error is called, it should raise SystemExit. We'll check its call.
    # argparse.ArgumentParser.error calls self.exit(2, message).
    # So, we can mock self.exit on the parser instance.
    mock_parser_instance.error = MagicMock(side_effect=SystemExit(2))

    # Patch sys.argv, and ArgumentParser to return our mock_parser_instance,
    # and parse_args on that instance to return our specifically crafted base_mock_args.
    # Other components are patched to avoid side effects, though they might not be reached.
    with (
        patch("sys.argv", test_argv),
        patch("argparse.ArgumentParser", return_value=mock_parser_instance) as MockArgumentParserClass,
        patch("google_scholar_scraper.main.ProxyManager"),
        patch("google_scholar_scraper.main.Fetcher"),
        patch("google_scholar_scraper.main.DataHandler"),
        patch("google_scholar_scraper.main.GraphBuilder"),
        patch("google_scholar_scraper.main.os.makedirs"),
        patch("google_scholar_scraper.main.logging.basicConfig"),
    ):
        # Configure the mock_parser_instance's parse_args method
        mock_parser_instance.parse_args.return_value = base_mock_args

        with pytest.raises(SystemExit) as e:
            await async_main_entry()

        assert e.value.code == 2  # argparse.error exits with code 2

        # Check that parser.error was called with a message containing the expected substring
        mock_parser_instance.error.assert_called_once()
        called_error_message = mock_parser_instance.error.call_args[0][0]
        assert expected_error_substring in called_error_message

        # Ensure ArgumentParser was instantiated (it is, to get the parser instance)
        MockArgumentParserClass.assert_called_once()


@pytest.mark.asyncio
async def test_main_no_proxies_available():
    """Test main function when NoProxiesAvailable is raised."""
    test_argv = ["main.py", "query_when_no_proxies"]  # Basic valid args
    mock_args = argparse.Namespace(
        query="query_when_no_proxies",
        authors=None,
        publication=None,
        year_low=None,
        year_high=None,
        num_results=10,
        output="no_proxy_out.csv",
        json=False,
        pdf_dir="no_proxy_pdfs",
        max_depth=3,
        graph_file="no_proxy_graph.graphml",
        log_level="INFO",
        phrase=None,
        exclude=None,
        title=None,
        author=None,
        source=None,
        min_citations=None,
        author_profile=None,
        recursive=False,
        graph_layout="spring",
        centrality_filter=None,
    )

    with (
        patch("sys.argv", test_argv),
        patch("argparse.ArgumentParser.parse_args", return_value=mock_args),
        patch("google_scholar_scraper.main.ProxyManager") as MockProxyManager,
        patch("google_scholar_scraper.main.Fetcher") as MockFetcher,
        patch("google_scholar_scraper.main.DataHandler") as MockDataHandler,
        patch("google_scholar_scraper.main.GraphBuilder") as MockGraphBuilder,
        patch("google_scholar_scraper.main.os.makedirs"),
        patch("google_scholar_scraper.main.logging.basicConfig"),
        patch("google_scholar_scraper.main.logging.error") as mock_logging_error,
    ):  # Patch logging.error
        mock_proxy_manager_instance = MockProxyManager.return_value
        # Configure get_working_proxies to raise NoProxiesAvailable
        mock_proxy_manager_instance.get_working_proxies = AsyncMock(side_effect=NoProxiesAvailable("Test no proxies"))
        mock_proxy_manager_instance.log_proxy_performance = MagicMock()

        mock_fetcher_instance = MockFetcher.return_value
        mock_fetcher_instance.scrape = AsyncMock()  # Should not be called if proxies fail
        mock_fetcher_instance.fetch_author_profile = AsyncMock()  # Should not be called
        mock_fetcher_instance.close = AsyncMock()

        mock_data_handler_instance = MockDataHandler.return_value
        mock_data_handler_instance.create_table = AsyncMock()  # Called before proxy check

        await async_main_entry()

        MockProxyManager.assert_called_once()
        mock_proxy_manager_instance.get_working_proxies.assert_called_once()

        # Assert logging.error was called due to NoProxiesAvailable
        mock_logging_error.assert_called_once()
        assert "No working proxies available" in mock_logging_error.call_args[0][0]

        # Assert that main processing did not occur
        mock_fetcher_instance.scrape.assert_not_called()
        mock_fetcher_instance.fetch_author_profile.assert_not_called()

        # Assert that cleanup in finally block still happens
        mock_fetcher_instance.close.assert_called_once()
        mock_proxy_manager_instance.log_proxy_performance.assert_called_once()

        # DataHandler.create_table is called before proxy check, so it should be called
        mock_data_handler_instance.create_table.assert_called_once()
