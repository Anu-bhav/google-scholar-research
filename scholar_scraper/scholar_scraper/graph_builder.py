# graph_builder.py
import networkx as nx


class GraphBuilder:
    def __init__(self):
        self.graph = nx.DiGraph()

    def add_citation(self, citing_title, citing_url, cited_by_url, cited_title=None):
        citing_node_id = citing_url or citing_title
        self.graph.add_node(citing_node_id, title=citing_title)
        cited_node_id = cited_by_url or "Unknown URL"
        cited_title = cited_title or cited_by_url or "Unknown Title"
        self.graph.add_node(cited_node_id, title=cited_title)
        if citing_node_id != cited_node_id:
            self.graph.add_edge(citing_node_id, cited_node_id)

    def save_graph(self, filename="citation_graph.graphml"):
        nx.write_graphml(self.graph, filename)

    def load_graph(self, filename="citation_graph.graphml"):
        try:
            self.graph = nx.read_graphml(filename)
        except FileNotFoundError:
            print(f"Graph file not found: {filename}")
