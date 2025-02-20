# graph_builder.py
import logging
import os  # Import os module for directory operations
from typing import Optional

import matplotlib.pyplot as plt  # Import matplotlib for visualization
import networkx as nx


class GraphBuilder:
    """Builds and manages a citation graph using networkx.

    Nodes in the graph represent academic papers, and edges represent citations
    between them.  Graph is persisted to and loaded from GraphML files.

    Supports graph visualization with customizable layouts and centrality-based filtering.
    Generates visualizations in 'graph_citations' folder by default, with spring, circular, and kamada_kawai layouts.
    """

    def __init__(self):
        """Initializes the GraphBuilder with an empty directed graph."""
        self.graph = nx.DiGraph()
        self.logger = logging.getLogger(__name__)
        self.output_folder = "graph_citations"  # Default output folder for graph files
        os.makedirs(self.output_folder, exist_ok=True)  # Ensure output folder exists

    def add_citation(self, citing_title, citing_url, cited_by_url, cited_title=None, citing_doi=None, cited_doi=None):
        """Adds a citation relationship to the graph.

        Nodes are created for both citing and cited papers.  If DOIs are available,
        they are used as primary node identifiers.  Titles and URLs are stored as
        node attributes.

        Args:
            citing_title (str): Title of the citing paper.
            citing_url (str, optional): URL of the citing paper.
            cited_by_url (str, optional): URL of the cited paper's "Cited by" page.
            cited_title (str, optional): Title of the cited paper (if known). Defaults to None.
            citing_doi (str, optional): DOI of the citing paper. Defaults to None.
            cited_doi (str, optional): DOI of the cited paper. Defaults to None.

        """
        citing_node_id = citing_doi if citing_doi else citing_url or citing_title  # DOI preferred as ID
        self.graph.add_node(
            citing_node_id, title=citing_title, url=citing_url, doi=citing_doi
        )  # Store title, URL, DOI as attributes

        cited_node_id = cited_doi if cited_doi else cited_by_url or cited_title or "Unknown Title"  # DOI preferred as ID
        cited_title = cited_title or cited_by_url or "Unknown Title"
        self.graph.add_node(
            cited_node_id, title=cited_title, url=cited_by_url, doi=cited_doi
        )  # Store title, URL, DOI as attributes

        if citing_node_id != cited_node_id:
            self.graph.add_edge(citing_node_id, cited_node_id)
            self.logger.debug(f"Added citation edge from '{citing_title}' to '{cited_title}'")
        else:
            self.logger.debug(f"Skipped self-citation for '{citing_title}'")

    def save_graph(self, filename="citation_graph.graphml"):
        """Saves the citation graph to a GraphML file in the 'graph_citations' folder.

        Args:
            filename (str, optional): The base filename to save the graph to.
                                     Defaults to "citation_graph.graphml".  Will be saved in 'graph_citations' folder.

        """
        full_filename = os.path.join(self.output_folder, filename)  # Save in output folder
        try:
            nx.write_graphml(self.graph, full_filename)
            self.logger.info(
                f"Citation graph saved to {full_filename} (GraphML format). "
                f"You can visualize it using tools like Gephi or Cytoscape for interactive exploration."
            )  # Note about visualization tools
        except Exception as e:
            self.logger.error(f"Error saving graph to {full_filename}: {e}", exc_info=True)

    def load_graph(self, filename="citation_graph.graphml"):
        """Loads a citation graph from a GraphML file in the 'graph_citations' folder.

        Handles FileNotFoundError and general exceptions during graph loading
        by starting with an empty graph and logging an error message.

        Args:
            filename (str, optional): The base filename to load the graph from.
                                     Defaults to "citation_graph.graphml". Will be loaded from 'graph_citations' folder.

        """
        full_filename = os.path.join(self.output_folder, filename)  # Load from output folder
        try:
            self.graph = nx.read_graphml(full_filename)
            self.logger.info(f"Graph loaded from {full_filename}")
        except FileNotFoundError:
            self.logger.warning(f"Graph file not found: {full_filename}. Starting with an empty graph.")
            self.graph = nx.DiGraph()  # Initialize empty graph if file not found
        except Exception as e:  # Catch XML parsing errors or other issues during loading
            self.logger.error(f"Error loading graph from {full_filename}: {e}. Starting with an empty graph.", exc_info=True)
            self.graph = nx.DiGraph()  # Initialize empty graph on error

    def calculate_degree_centrality(self):
        """Calculates and stores in-degree and out-degree centrality as node attributes."""
        in_degree_centrality = nx.in_degree_centrality(self.graph)
        out_degree_centrality = nx.out_degree_centrality(self.graph)
        nx.set_node_attributes(self.graph, in_degree_centrality, "in_degree_centrality")
        nx.set_node_attributes(self.graph, out_degree_centrality, "out_degree_centrality")
        self.logger.info("Calculated and stored degree centrality measures.")

    def visualize_graph(self, filename="citation_graph.png", layout="spring", filter_by_centrality: Optional[float] = None):
        """Visualizes the citation graph and saves it to a PNG file in 'graph_citations' folder.

        Nodes are sized based on their in-degree centrality.

        Args:
            filename (str, optional): The base filename to save the visualization to
                                     (as a PNG image). Defaults to "citation_graph.png". Will be saved in 'graph_citations' folder.
            layout (str, optional):  Layout algorithm to use for visualization.
                                      Options: 'spring' (default), 'circular', 'kamada_kawai'.
                                      Defaults to 'spring'.
            filter_by_centrality (float, optional):  Minimum in-degree centrality value to display nodes.
                                                     Nodes with centrality below this threshold will be filtered out.
                                                     Defaults to None (no filtering).

        """
        full_filename = os.path.join(self.output_folder, filename)  # Save in output folder
        try:
            if not self.graph.nodes():
                self.logger.warning("Graph is empty, no visualization to create.")
                return

            self.calculate_degree_centrality()  # Calculate centrality before visualization

            plt.figure(figsize=(12, 12))  # Adjust figure size as needed

            # Layout selection
            layout_functions = {
                "spring": nx.spring_layout,
                "circular": nx.circular_layout,
                "kamada_kawai": nx.kamada_kawai_layout,
                # Add more layouts here if needed
            }
            layout_func = layout_functions.get(layout, nx.spring_layout)  # Default to spring if layout is invalid
            pos = layout_func(self.graph)

            # Node size based on in-degree centrality (adjust multiplier as needed)
            node_size = [
                v * 5000 for v in nx.get_node_attributes(self.graph, "in_degree_centrality").values()
            ]  # Multiplier for visibility

            # Node filtering based on centrality
            nodes_to_draw = self.graph.nodes()  # Default to all nodes
            if filter_by_centrality is not None:
                nodes_to_draw = [
                    node
                    for node, centrality in nx.get_node_attributes(self.graph, "in_degree_centrality").items()
                    if centrality >= filter_by_centrality
                ]
                subgraph = self.graph.subgraph(nodes_to_draw)  # Create subgraph with filtered nodes
            else:
                subgraph = self.graph  # Use the full graph if no filtering

            nx.draw(
                subgraph,  # Draw the subgraph (or full graph if no filtering)
                pos,
                with_labels=False,  # Labels can clutter large graphs
                node_size=[
                    node_size[list(self.graph.nodes()).index(n)] for n in subgraph.nodes()
                ],  # Size nodes based on their original centrality in full graph
                node_color="skyblue",
                arrowsize=10,
                alpha=0.7,
            )
            title = "Citation Graph Visualization (Node Size by In-Degree Centrality)"
            if filter_by_centrality is not None:
                title += f" - Centrality Filter >= {filter_by_centrality}"  # Add filter info to title
            plt.title(title)
            plt.savefig(full_filename)  # Save to output folder
            self.logger.info(
                f"Citation graph visualization saved to {full_filename} (Layout: {layout}, Node size reflects citation count"
                + (f", Filtered by centrality >= {filter_by_centrality})" if filter_by_centrality is not None else ")")
            )  # Updated log with layout and filter info
            plt.close()  # Close the figure to free memory
        except Exception as e:
            self.logger.error(f"Error during graph visualization: {e}", exc_info=True)
            self.logger.warning("Graph visualization failed.")

    def generate_default_visualizations(self, base_filename="citation_graph"):
        """Generates default visualizations of the citation graph with different layouts.

        Saves PNG files to the 'graph_citations' folder for spring, circular, and kamada_kawai layouts.

        Args:
            base_filename (str, optional): Base filename for the visualization files.
                                            Layout name will be appended to this base name.
                                            Defaults to "citation_graph".

        """
        layouts = ["spring", "circular", "kamada_kawai"]
        for layout in layouts:
            filename = f"{base_filename}_{layout}_layout.png"
            self.visualize_graph(filename=filename, layout=layout)
        self.logger.info(
            f"Generated default visualizations in '{self.output_folder}' folder: {', '.join([f'{base_filename}_{layout}_layout.png' for layout in layouts])}"
        )
