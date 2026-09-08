import numpy as np
import networkx as nx


def build_google_matrix(A, alpha=0.85):

    if isinstance(A, nx.DiGraph):
        nodes = sorted(A.nodes())
        A = nx.to_numpy_array(A, nodelist=nodes)

    A = np.asarray(A, dtype=float)
    N = A.shape[0]

    # E is column-stochastic: column j = outgoing links of node j, normalized
    E = np.zeros((N, N))
    for j in range(N):
        outdeg = A[j, :].sum()
        if outdeg == 0:
            E[:, j] = 1.0 / N          # dangling node, spread equally
        else:
            E[:, j] = A[j, :] / outdeg

    G = alpha * E + (1.0 - alpha) / N * np.ones((N, N))
    return G


def classical_pagerank(G, tol=1e-12, max_iter=10000):
    # power iteration until the vector stops changing
    N = G.shape[0]
    I = np.ones(N) / N
    for _ in range(max_iter):
        I_new = G @ I
        I_new /= I_new.sum()
        if np.max(np.abs(I_new - I)) < tol:
            return I_new
        I = I_new
    return I


def initial_state(G):
    # starting walker state, built from sqrt(G)
    N = G.shape[0]
    return np.sqrt(G).T / np.sqrt(N)


def _rowwise_projection(Psi, sqrtG):
    # projection part of U, done row by row
    coeff = np.einsum('kj,jk->j', sqrtG, Psi)
    return sqrtG.T * coeff[:, None]


def apply_U(Psi, sqrtG):
    # one step of U = S(2*Pi - 1)

    return (2.0 * _rowwise_projection(Psi, sqrtG) - Psi).T


def quantum_pagerank(G, T=None, block=200, conv_tol=1e-4, T_cap=10000):

    N = G.shape[0]
    sqrtG = np.sqrt(G)
    Psi = initial_state(G)

    series = []

    def step_once(state):
        iq = np.sum(np.abs(state) ** 2, axis=0)   # I_q(P_i, t) for all i
        return iq, apply_U(state, sqrtG)

    if T is not None:
        for _ in range(T):
            iq, Psi = step_once(Psi)
            series.append(iq)
        Iq_series = np.array(series)
        return Iq_series, Iq_series.mean(axis=0), T

    # no fixed T given, so keep running in blocks until the average settles
    prev_avg = None
    T_used = 0
    while T_used < T_cap:
        for _ in range(block):
            iq, Psi = step_once(Psi)
            series.append(iq)
        T_used += block
        Iq_series = np.array(series)
        avg = Iq_series.mean(axis=0)
        if prev_avg is not None and np.max(np.abs(avg - prev_avg)) < conv_tol:
            break
        prev_avg = avg

    Iq_series = np.array(series)
    return Iq_series, Iq_series.mean(axis=0), T_used
