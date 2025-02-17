# scholar_scraper/scholar_scraper/graph_builder.py
import networkx as nx


class GraphBuilder:
    def __init__(self):
        self.graph = nx.DiGraph()

    def add_citation(self, citing_title, citing_url, cited_by_url):
        # Use URLs as unique node IDs (you might need a better ID scheme)
        if citing_url:
            self.graph.add_node(citing_url, title=citing_title)  # Add the node, with the title
        else:
            self.graph.add_node(citing_title, title=citing_title)  # if no citing url, use title.
        # Extract cited title
        if cited_by_url:
            cited_title = cited_by_url  # Placeholder, extract actual cited title from cited_by_url content
            self.graph.add_node(cited_by_url, title=cited_title)  # Add the cited node
            if citing_url:
                self.graph.add_edge(citing_url, cited_by_url)  # Add the edge (citation)
            else:
                self.graph.add_edge(citing_title, cited_by_url)
