import os
from unittest.mock import call, patch

import networkx as nx
import pytest
from google_scholar_scraper.graph_builder import GraphBuilder


@pytest.fixture
def graph_builder(tmp_path):
    """Fixture to provide a GraphBuilder instance with a temporary output folder."""
    # Patch os.makedirs for the default __init__ call, though we override output_folder
    with patch("os.makedirs") as mock_original_makedirs:
        gb = GraphBuilder()

    # Override output_folder to use tmp_path for test isolation
    test_output_folder = tmp_path / "test_graph_citations"
    os.makedirs(test_output_folder, exist_ok=True)  # Ensure this temp dir exists for tests
    gb.output_folder = str(test_output_folder)  # GraphBuilder expects a string path

    # Reset graph for each test using this fixture to ensure independence
    gb.graph = nx.DiGraph()
    yield gb
    # tmp_path is automatically cleaned up by pytest


def test_graph_builder_initialization(graph_builder):
    """Test the initialization of the GraphBuilder."""
    gb = graph_builder  # Get instance from fixture

    assert isinstance(gb.graph, nx.DiGraph), "Graph should be a networkx DiGraph."
    assert gb.graph.number_of_nodes() == 0, "Graph should be initialized empty (no nodes)."
    assert gb.graph.number_of_edges() == 0, "Graph should be initialized empty (no edges)."
    # The output_folder is now the temp path
    assert os.path.isdir(gb.output_folder), "Test output folder should exist."
    assert "test_graph_citations" in gb.output_folder, "Output folder should be the test one."


def test_add_citation_simple(graph_builder):
    """Test adding a simple citation with DOIs."""
    gb = graph_builder

    citing_data = {"title": "Citing Paper A", "url": "http://example.com/citingA", "doi": "10.1/citingA"}
    cited_data = {
        "title": "Cited Paper B",
        "url": "http://example.com/citedB_by_url",  # This is cited_by_url
        "doi": "10.1/citedB",
    }

    gb.add_citation(
        citing_title=citing_data["title"],
        citing_url=citing_data["url"],
        cited_by_url=cited_data["url"],  # Simulating cited_by_url
        cited_title=cited_data["title"],
        citing_doi=citing_data["doi"],
        cited_doi=cited_data["doi"],
    )

    assert gb.graph.number_of_nodes() == 2
    assert gb.graph.number_of_edges() == 1

    citing_node_id = citing_data["doi"]
    cited_node_id = cited_data["doi"]

    assert citing_node_id in gb.graph
    assert cited_node_id in gb.graph

    assert gb.graph.has_edge(citing_node_id, cited_node_id)

    # Check attributes of citing node
    citing_node_attrs = gb.graph.nodes[citing_node_id]
    assert citing_node_attrs["title"] == citing_data["title"]
    assert citing_node_attrs["url"] == citing_data["url"]
    assert citing_node_attrs["doi"] == citing_data["doi"]

    # Check attributes of cited node
    # Note: add_citation stores cited_by_url in the 'url' attribute of the cited node
    cited_node_attrs = gb.graph.nodes[cited_node_id]
    assert cited_node_attrs["title"] == cited_data["title"]
    assert cited_node_attrs["url"] == cited_data["url"]  # This was cited_by_url
    assert cited_node_attrs["doi"] == cited_data["doi"]


def test_add_citation_self_citation(graph_builder):
    """Test that adding a self-citation does not create an edge."""
    gb = graph_builder

    paper_doi = "10.1234/selfcite"
    paper_title = "A Paper Citing Itself"
    paper_url = "http://example.com/selfcite"

    gb.add_citation(
        citing_title=paper_title,
        citing_url=paper_url,
        cited_by_url=paper_url,  # Using same URL for cited_by_url for simplicity
        cited_title=paper_title,
        citing_doi=paper_doi,
        cited_doi=paper_doi,  # Same DOI for citing and cited
    )

    assert gb.graph.number_of_nodes() == 1, "Should only create one node for a self-citation."
    assert gb.graph.number_of_edges() == 0, "Should not create an edge for a self-citation."

    node_id = paper_doi
    assert node_id in gb.graph
    node_attrs = gb.graph.nodes[node_id]
    assert node_attrs["title"] == paper_title
    assert node_attrs["url"] == paper_url  # Citing URL is stored
    assert node_attrs["doi"] == paper_doi


def test_add_citation_node_id_precedence(graph_builder):
    """Test node ID precedence (DOI > URL > Title)."""
    gb = graph_builder

    # Scenario 1: DOI present, should be used as ID
    gb.add_citation(
        citing_title="Title C1",
        citing_url="http://example.com/urlC1",
        citing_doi="doi_C1",
        cited_title="Title D1",
        cited_by_url="http://example.com/urlD1_by",
        cited_doi="doi_D1",
    )
    assert "doi_C1" in gb.graph
    assert "doi_D1" in gb.graph
    assert gb.graph.has_edge("doi_C1", "doi_D1")
    assert gb.graph.nodes["doi_C1"]["title"] == "Title C1"
    assert gb.graph.nodes["doi_D1"]["title"] == "Title D1"

    # Reset graph for next scenario by re-initializing (fixture handles tmp_path persistence if needed for other tests)
    gb.graph = nx.DiGraph()

    # Scenario 2: No DOI, URL present, URL should be used as ID
    gb.add_citation(
        citing_title="Title C2",
        citing_url="http://example.com/urlC2",
        citing_doi=None,
        cited_title="Title D2",
        cited_by_url="http://example.com/urlD2_by",
        cited_doi=None,
    )
    assert "http://example.com/urlC2" in gb.graph
    assert "http://example.com/urlD2_by" in gb.graph  # cited_node_id uses cited_by_url if no DOI
    assert gb.graph.has_edge("http://example.com/urlC2", "http://example.com/urlD2_by")
    assert gb.graph.nodes["http://example.com/urlC2"]["title"] == "Title C2"
    assert gb.graph.nodes["http://example.com/urlD2_by"]["title"] == "Title D2"

    gb.graph = nx.DiGraph()

    # Scenario 3: No DOI, No URL for citing_url, Title should be used for citing_node_id
    # For cited_node_id, if cited_by_url is also None, then cited_title is used.
    gb.add_citation(
        citing_title="Title C3", citing_url=None, citing_doi=None, cited_title="Title D3", cited_by_url=None, cited_doi=None
    )
    assert "Title C3" in gb.graph
    assert "Title D3" in gb.graph
    assert gb.graph.has_edge("Title C3", "Title D3")
    assert gb.graph.nodes["Title C3"]["title"] == "Title C3"
    assert gb.graph.nodes["Title D3"]["title"] == "Title D3"

    gb.graph = nx.DiGraph()

    # Scenario 4: Citing has DOI, Cited has only Title (no DOI, no cited_by_url)
    gb.add_citation(
        citing_title="Title C4",
        citing_url="http://example.com/urlC4",
        citing_doi="doi_C4",
        cited_title="Title D4",
        cited_by_url=None,
        cited_doi=None,
    )
    assert "doi_C4" in gb.graph
    assert "Title D4" in gb.graph
    assert gb.graph.has_edge("doi_C4", "Title D4")
    assert gb.graph.nodes["Title D4"]["title"] == "Title D4"
    assert gb.graph.nodes["Title D4"]["url"] is None  # No cited_by_url provided

    gb.graph = nx.DiGraph()

    # Scenario 5: Citing has only Title, Cited has URL (no DOI)
    # Citing node ID: citing_title
    # Cited node ID: cited_by_url
    gb.add_citation(
        citing_title="Title C5",
        citing_url=None,
        citing_doi=None,
        cited_title="Title D5",
        cited_by_url="http://example.com/urlD5_by",
        cited_doi=None,
    )
    assert "Title C5" in gb.graph
    assert "http://example.com/urlD5_by" in gb.graph
    assert gb.graph.has_edge("Title C5", "http://example.com/urlD5_by")
    assert gb.graph.nodes["http://example.com/urlD5_by"]["title"] == "Title D5"
    assert gb.graph.nodes["http://example.com/urlD5_by"]["url"] == "http://example.com/urlD5_by"


def test_add_citation_cited_title_fallback(graph_builder):
    """Test fallback logic for cited paper's title and node ID."""
    gb = graph_builder

    # Scenario 1: cited_title is None, cited_by_url is present
    # Expected cited_node_id = cited_by_url (as cited_doi is None)
    # Expected cited_node_title = cited_by_url
    citing_paper_1 = "doi_citing_1"
    cited_url_1 = "http://example.com/cited_by_url_1"

    gb.add_citation(
        citing_title="Citing Paper 1",
        citing_url="http://example.com/dummy_citing_S1",
        citing_doi=citing_paper_1,
        cited_title=None,
        cited_by_url=cited_url_1,
        cited_doi=None,
    )
    assert cited_url_1 in gb.graph  # Node ID should be the URL
    assert gb.graph.nodes[cited_url_1]["title"] == cited_url_1
    assert gb.graph.nodes[cited_url_1]["url"] == cited_url_1  # URL attribute also gets cited_by_url
    assert gb.graph.has_edge(citing_paper_1, cited_url_1)

    gb.graph = nx.DiGraph()  # Reset for next scenario

    # Scenario 2: cited_title is None, cited_by_url is None
    # Expected cited_node_id = "Unknown Title" (as cited_doi is None)
    # Expected cited_node_title = "Unknown Title"
    citing_paper_2 = "doi_citing_2"

    gb.add_citation(
        citing_title="Citing Paper 2",
        citing_url="http://example.com/dummy_citing_S2",
        citing_doi=citing_paper_2,
        cited_title=None,
        cited_by_url=None,
        cited_doi=None,
    )
    unknown_title_node_id = "Unknown Title"  # Default ID if title, URL, DOI are all None for cited

    # Check if the node "Unknown Title" was created.
    # The logic is: cited_node_id = cited_doi if cited_doi else cited_by_url or cited_title or "Unknown Title"
    # If all are None, cited_title becomes "Unknown Title", and cited_node_id becomes "Unknown Title".
    assert unknown_title_node_id in gb.graph
    assert gb.graph.nodes[unknown_title_node_id]["title"] == "Unknown Title"
    assert gb.graph.nodes[unknown_title_node_id]["url"] is None  # No URL provided
    assert gb.graph.nodes[unknown_title_node_id]["doi"] is None  # No DOI provided
    assert gb.graph.has_edge(citing_paper_2, unknown_title_node_id)

    gb.graph = nx.DiGraph()

    # Scenario 3: cited_title is provided, cited_by_url is None, cited_doi is None
    # Expected cited_node_id = "Explicit Cited Title"
    # Expected cited_node_title = "Explicit Cited Title"
    citing_paper_3 = "doi_citing_3"
    explicit_cited_title = "Explicit Cited Title"
    gb.add_citation(
        citing_title="Citing Paper 3",
        citing_url="http://example.com/dummy_citing_S3",
        citing_doi=citing_paper_3,
        cited_title=explicit_cited_title,
        cited_by_url=None,
        cited_doi=None,
    )
    assert explicit_cited_title in gb.graph
    assert gb.graph.nodes[explicit_cited_title]["title"] == explicit_cited_title
    assert gb.graph.has_edge(citing_paper_3, explicit_cited_title)


def test_save_and_load_graph(graph_builder):
    """Test saving a graph to GraphML and loading it back."""
    gb = graph_builder
    test_filename = "test_citation_graph.graphml"
    full_file_path = os.path.join(gb.output_folder, test_filename)

    # 1. Add some data to the graph
    citing_doi1 = "10.1/paper1"
    cited_doi1 = "10.1/paper2"
    citing_doi2 = "10.1/paper3"  # paper3 cites paper1

    gb.add_citation(
        citing_title="Paper 1",
        citing_url="url1",
        citing_doi=citing_doi1,
        cited_title="Paper 2",
        cited_by_url="url2_by",
        cited_doi=cited_doi1,
    )
    gb.add_citation(
        citing_title="Paper 3",
        citing_url="url3",
        citing_doi=citing_doi2,
        cited_title="Paper 1",
        cited_by_url="url1_by",
        cited_doi=citing_doi1,  # paper3 cites paper1
    )

    original_nodes = dict(gb.graph.nodes(data=True))
    original_edges = list(gb.graph.edges())
    original_num_nodes = gb.graph.number_of_nodes()
    original_num_edges = gb.graph.number_of_edges()

    assert original_num_nodes > 0, "Graph should have nodes before saving."

    # 2. Save the graph
    gb.save_graph(filename=test_filename)
    assert os.path.exists(full_file_path), f"Graph file {full_file_path} should exist after saving."

    # 3. Clear the current graph and load from file
    gb.graph = nx.DiGraph()  # Clear in-memory graph
    assert gb.graph.number_of_nodes() == 0, "Graph should be empty before loading."

    gb.load_graph(filename=test_filename)

    # 4. Assertions on the loaded graph
    assert gb.graph.number_of_nodes() == original_num_nodes, "Loaded graph should have same number of nodes."
    assert gb.graph.number_of_edges() == original_num_edges, "Loaded graph should have same number of edges."

    loaded_nodes = dict(gb.graph.nodes(data=True))
    assert loaded_nodes == original_nodes, "Node data should be preserved after loading."

    loaded_edges = list(gb.graph.edges())
    assert sorted(loaded_edges) == sorted(original_edges), "Edges should be preserved after loading."

    # Specific checks
    assert citing_doi1 in gb.graph
    assert gb.graph.nodes[citing_doi1]["title"] == "Paper 1"
    assert gb.graph.has_edge(citing_doi2, citing_doi1)


def test_load_graph_file_not_found(graph_builder):
    """Test loading a graph when the GraphML file does not exist."""
    gb = graph_builder

    # Ensure the graph is initially empty or has some state
    gb.add_citation("Initial Title", "initial_url", "initial_cited_by", "Initial Cited Title")
    assert gb.graph.number_of_nodes() > 0, "Graph should have content before attempting to load non-existent file."

    # Attempt to load a non-existent file
    # The load_graph method uses gb.output_folder, which is a temp dir here.
    # We don't need to mock os.path.exists, as the file truly won't exist in tmp_path.
    gb.load_graph(filename="this_file_does_not_exist.graphml")

    # Assert that the graph is now empty as per the error handling
    assert isinstance(gb.graph, nx.DiGraph), "Graph should be a networkx DiGraph."
    assert gb.graph.number_of_nodes() == 0, "Graph should be empty after failing to load non-existent file."
    assert gb.graph.number_of_edges() == 0, "Graph should have no edges after failing to load non-existent file."


def test_calculate_degree_centrality(graph_builder):
    """Test calculation and storage of degree centrality."""
    gb = graph_builder

    # Create a known graph structure
    # Using simple titles as node IDs for this test, assuming no DOIs/URLs provided to add_citation
    # to force titles to be IDs. Or, use DOIs consistently. Let's use DOIs for clarity.
    node_a_doi = "doi_A"
    node_b_doi = "doi_B"
    node_c_doi = "doi_C"
    node_d_doi = "doi_D"

    # A -> B
    gb.add_citation(
        citing_title="Paper A",
        citing_url="urlA",
        citing_doi=node_a_doi,
        cited_title="Paper B",
        cited_by_url="urlB_by",
        cited_doi=node_b_doi,
    )
    # A -> C
    gb.add_citation(
        citing_title="Paper A",
        citing_url="urlA",
        citing_doi=node_a_doi,  # Node A already exists
        cited_title="Paper C",
        cited_by_url="urlC_by",
        cited_doi=node_c_doi,
    )
    # D -> B
    gb.add_citation(
        citing_title="Paper D",
        citing_url="urlD",
        citing_doi=node_d_doi,
        cited_title="Paper B",
        cited_by_url="urlB_by",
        cited_doi=node_b_doi,
    )  # Node B already exists

    assert gb.graph.number_of_nodes() == 4  # A, B, C, D
    assert gb.graph.number_of_edges() == 3  # A->B, A->C, D->B

    gb.calculate_degree_centrality()

    nodes_data = gb.graph.nodes(data=True)

    # N-1 for centrality calculation (N=4, so N-1=3)
    # networkx.degree_centrality divides by N-1 for non-empty graphs with >1 node.
    # If N=1, centrality is 0. If graph is empty, it's an empty dict.
    # Here N=4.
    denominator = float(len(gb.graph) - 1) if len(gb.graph) > 1 else 1.0
    if denominator == 0:
        denominator = 1.0  # Avoid division by zero for single node graph, though N=4 here

    expected_centralities = {
        node_a_doi: {"in": 0.0, "out": 2.0 / denominator},  # Out-degree 2
        node_b_doi: {"in": 2.0 / denominator, "out": 0.0},  # In-degree 2
        node_c_doi: {"in": 1.0 / denominator, "out": 0.0},  # In-degree 1
        node_d_doi: {"in": 0.0, "out": 1.0 / denominator},  # Out-degree 1
    }

    for node_id, attrs in nodes_data:
        assert "in_degree_centrality" in attrs
        assert "out_degree_centrality" in attrs
        assert attrs["in_degree_centrality"] == pytest.approx(expected_centralities[node_id]["in"])
        assert attrs["out_degree_centrality"] == pytest.approx(expected_centralities[node_id]["out"])


@patch("google_scholar_scraper.graph_builder.plt")  # Mock the entire plt module used by graph_builder
@patch("google_scholar_scraper.graph_builder.nx")  # Mock the entire nx module used by graph_builder
def test_visualize_graph_calls_draw_and_save(mock_nx, mock_plt, graph_builder):
    """Test that visualize_graph calls relevant plotting and saving functions."""
    gb = graph_builder

    # Add a node to make the graph non-empty
    gb.add_citation("Test Paper", "test_url", "cited_by_test", "Cited Test Paper", "doi_test", "doi_cited_test")
    assert gb.graph.number_of_nodes() > 0

    # Mock specific functions/methods that are called
    # calculate_degree_centrality is a method of gb, so patch it on the instance or class
    with patch.object(gb, "calculate_degree_centrality") as mock_calc_centrality:
        # Configure mock_nx layout function to return some positions
        mock_nx.spring_layout.return_value = {"doi_test": (0, 0), "doi_cited_test": (1, 1)}
        # Configure get_node_attributes to return something plausible for centrality
        mock_nx.get_node_attributes.return_value = {"doi_test": 0.5, "doi_cited_test": 0.5}

        test_viz_filename = "test_visualization.png"
        gb.visualize_graph(filename=test_viz_filename, layout="spring")

        mock_calc_centrality.assert_called_once()

        mock_plt.figure.assert_called_once()
        mock_nx.spring_layout.assert_called_once_with(gb.graph)
        mock_nx.draw.assert_called_once()

        # Check arguments of nx.draw if necessary, e.g., graph, pos
        # args, kwargs = mock_nx.draw.call_args
        # assert args[0] is gb.graph # First arg is the graph
        # assert "node_size" in kwargs

        mock_plt.title.assert_called_once()

        expected_save_path = os.path.join(gb.output_folder, test_viz_filename)
        mock_plt.savefig.assert_called_once_with(expected_save_path)
        mock_plt.close.assert_called_once()


def test_visualize_graph_empty_graph(graph_builder):
    """Test visualize_graph behavior with an empty graph."""
    gb = graph_builder
    assert gb.graph.number_of_nodes() == 0  # Ensure graph is empty

    with (
        patch.object(gb.logger, "warning") as mock_logger_warning,
        patch("google_scholar_scraper.graph_builder.plt.savefig") as mock_savefig,
    ):
        gb.visualize_graph(filename="empty_graph_viz.png")

        mock_logger_warning.assert_called_once_with("Graph is empty, no visualization to create.")
        mock_savefig.assert_not_called()


def test_visualize_graph_with_centrality_filter(graph_builder):
    """Test visualize_graph with node filtering based on in-degree centrality."""
    gb = graph_builder

    # Create a graph: A->B, C->B, D->B. B has high in-degree. E is isolated.
    node_A = "doi_A"
    node_B = "doi_B"
    node_C = "doi_C"
    node_D = "doi_D"
    node_E = "doi_E"  # Isolated node

    # Add citations ensuring all necessary attributes are present for node creation
    gb.add_citation(
        citing_title="A", citing_url="urlA", citing_doi=node_A, cited_title="B", cited_by_url="urlB_by_A", cited_doi=node_B
    )
    gb.add_citation(
        citing_title="C", citing_url="urlC", citing_doi=node_C, cited_title="B", cited_by_url="urlB_by_C", cited_doi=node_B
    )
    gb.add_citation(
        citing_title="D", citing_url="urlD", citing_doi=node_D, cited_title="B", cited_by_url="urlB_by_D", cited_doi=node_B
    )
    gb.graph.add_node(node_E, title="E", url="urlE", doi=node_E)  # Ensure E has attributes too

    # calculate_degree_centrality will be called by visualize_graph.
    # Expected centralities (N=5, N-1=4 for denominator)
    # B: in-degree 3 -> in-centrality = 3/4 = 0.75
    # A, C, D, E: in-degree 0 -> in-centrality = 0

    # Patch necessary drawing and plotting functions
    with (
        patch("google_scholar_scraper.graph_builder.plt") as mock_plt,
        patch("google_scholar_scraper.graph_builder.nx.draw") as mock_nx_draw,
        patch("google_scholar_scraper.graph_builder.nx.spring_layout") as mock_nx_spring_layout,
    ):
        # Configure mock layout to return dummy positions
        mock_nx_spring_layout.return_value = {n: (0, 0) for n in gb.graph.nodes()}

        # Filter threshold: only nodes with in-degree centrality >= 0.5
        # In our setup, only node B (0.75) should pass.
        gb.visualize_graph(filename="filtered_viz.png", layout="spring", filter_by_centrality=0.5)

        mock_plt.figure.assert_called_once()
        mock_nx_spring_layout.assert_called_once_with(gb.graph)  # It will be called with the full graph

        mock_nx_draw.assert_called_once()
        args, kwargs = mock_nx_draw.call_args
        drawn_subgraph = args[0]  # The first positional argument to nx.draw is the graph/subgraph

        mock_plt.title.assert_called_once()
        expected_save_path = os.path.join(gb.output_folder, "filtered_viz.png")
        mock_plt.savefig.assert_called_once_with(expected_save_path)
        mock_plt.close.assert_called_once()

        # Assertions on the subgraph that was drawn
        assert isinstance(drawn_subgraph, nx.DiGraph)
        # The order of nodes in list(drawn_subgraph.nodes()) might not be guaranteed, so check presence/absence
        assert len(list(drawn_subgraph.nodes())) == 1
        assert node_B in drawn_subgraph
        assert node_A not in drawn_subgraph
        assert node_C not in drawn_subgraph
        assert node_D not in drawn_subgraph
        assert node_E not in drawn_subgraph

    def test_generate_default_visualizations_calls_visualize_graph(graph_builder):
        """Test that generate_default_visualizations calls visualize_graph correctly."""
        gb = graph_builder

        # Add a node to make the graph non-empty, so visualize_graph doesn't exit early
        gb.add_citation("Test Paper", "test_url", "cited_by_test", "Cited Test Paper", "doi_test", "doi_cited_test")

        base_filename_to_test = "my_custom_base"

        with patch.object(gb, "visualize_graph") as mock_visualize_graph:
            gb.generate_default_visualizations(base_filename=base_filename_to_test)

            assert mock_visualize_graph.call_count == 3

            expected_calls = [
                call(filename=f"{base_filename_to_test}_spring_layout.png", layout="spring"),
                call(filename=f"{base_filename_to_test}_circular_layout.png", layout="circular"),
                call(filename=f"{base_filename_to_test}_kamada_kawai_layout.png", layout="kamada_kawai"),
            ]
            # mock_visualize_graph.assert_has_calls(expected_calls, any_order=False)
            # Using any_order=False by default. If order is not guaranteed, use any_order=True
            # For more robust checking, iterate through call_args_list:

            calls = mock_visualize_graph.call_args_list

            # Check spring layout call
            args, kwargs = calls[0]
            assert kwargs.get("filename") == f"{base_filename_to_test}_spring_layout.png"
            assert kwargs.get("layout") == "spring"

            # Check circular layout call
            args, kwargs = calls[1]
            assert kwargs.get("filename") == f"{base_filename_to_test}_circular_layout.png"
            assert kwargs.get("layout") == "circular"

            # Check kamada_kawai layout call
            args, kwargs = calls[2]
            assert kwargs.get("filename") == f"{base_filename_to_test}_kamada_kawai_layout.png"
            assert kwargs.get("layout") == "kamada_kawai"
