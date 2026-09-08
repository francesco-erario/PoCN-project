import networkx as nx


def directed_erdos_renyi(N=128, p=0.05, seed=0, max_tries=20):
    # try new seeds until we get a weakly connected graph
    for t in range(max_tries):
        G = nx.gnp_random_graph(N, p, seed=seed + t, directed=True)
        if nx.is_weakly_connected(G):
            return G
    raise RuntimeError(f"no weakly connected G(N={N}, p={p}) in {max_tries} tries")


def directed_scale_free(N=128, seed=0):

    M = nx.scale_free_graph(N, seed=seed)
    G = nx.DiGraph()
    G.add_nodes_from(range(N))
    for u, v in M.edges():
        if u != v:
            G.add_edge(u, v)
    return G


def build_hierarchical(n):

    if n == 1:
        nodes = [0, 1, 2]
        edges = [(0, 1), (1, 2), (2, 0)]      # hub -> second -> third -> hub
        return nodes, edges, 0, 1, 2

    a_nodes, a_edges, a_hub, a_second, a_third = build_hierarchical(n - 1)
    size = len(a_nodes)

    # make 3 copies of the smaller graph, shifted by offset 0, size, 2*size
    copies = []
    for c in range(3):
        off = c * size
        nodes_c = [x + off for x in a_nodes]
        edges_c = [(u + off, v + off) for (u, v) in a_edges]
        copies.append((nodes_c, edges_c, a_hub + off, a_second + off,
                       a_third + off))

    (A_nodes, A_edges, A_hub, A_second, A_third) = copies[0]
    (B_nodes, B_edges, B_hub, B_second, B_third) = copies[1]
    (C_nodes, C_edges, C_hub, C_second, C_third) = copies[2]

    nodes = A_nodes + B_nodes + C_nodes
    edges = A_edges + B_edges + C_edges
    edges += [
        (A_hub, B_hub),        # hub_A -> hub_B
        (B_hub, C_hub),        # hub_B -> hub_C
        (A_hub, C_hub),        # hub_A -> hub_C (transitive, not a cycle)
        (A_hub, B_second),     # hub_A -> second_B
        (A_hub, C_third),      # hub_A -> third_C
        (A_second, C_second),  # second_A -> second_C
        (A_third, B_third),    # third_A -> third_B
    ]
    return nodes, edges, A_hub, B_hub, C_hub


def hierarchical_digraph(n):
    # wraps build_hierarchical(n) into a networkx DiGraph
    nodes, edges, _, _, _ = build_hierarchical(n)
    G = nx.DiGraph()
    G.add_nodes_from(nodes)
    G.add_edges_from(edges)
    return G
