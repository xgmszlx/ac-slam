#!/usr/bin/env python3
"""Read-only audit: pre-probe graph-geodesic separation and D-opt marginal utility.

For a sentinel suite produced by the realizability pilot, this tool reads the
saved `pose_graph_before.json` / `pose_graph_after.json` (exact full Karto node
and edge sets with covariance) and computes, for every newly created edge:

  * `geodesic_hops_pre`           - hop count of the shortest path between the
                                    two endpoints in the PRE-probe graph;
  * `geodesic_length_pre_m`       - Euclidean-length shortest path between the
                                    endpoints in the PRE-probe graph;
  * `edge_length_m`               - Euclidean length of the new edge itself;
  * `cycle_length_m`              - geodesic_length_pre_m + edge_length_m, i.e.
                                    the length of the cycle closed by the edge;
  * `bridges_components_pre`      - True when the endpoints were in different
                                    pre-probe components (no pre-probe path).

It then evaluates the realized graph with the ORIGINAL project utility and
reports conditional marginal contributions:

  weight(edge)  = utils.get_d_opt(information matrix)           [utils.py:115]
  information    = covariance^-1                                 (project convention)
  U(graph)       = utils.get_normalized_weighted_spanning_trees(graph, "D-opt")
                 = exp(mean(log(eigenvalues > 1e-6)))            [utils.py:139]

  dU_target  = U(G_all) - U(G_all - E_target)
  dU_history = U(G_all) - U(G_all - E_history)   (target + wrong-target edges)

These differences are CONDITIONAL MARGINAL CONTRIBUTIONS given the rest of the
realized graph. They are NOT Shapley values and NOT absolute causal effects: the
edge sets are not exchangeable and their removal order is arbitrary.

The tool is read-only: no planner, mapper, matcher threshold, route, seed, or
outcome definition is touched. It only analyzes already-saved graphs.
"""

import argparse
import csv
import json
import math
import sys
from pathlib import Path

import networkx as nx
import numpy as np

EIG_TH = 1e-6  # matches baseline/.../scripts/utils.py:13

# The paper's own utility functions (replicated verbatim from
# baseline/Graph-Based_SLAM-Aware_Exploration/scripts/utils.py to avoid importing
# the plotting/rospy stack; formulas are identical).
#
# utils.py:115 get_d_opt(A):        exp(sum(log(eigv[eigv > EIG_TH])) / n)
# utils.py:139 get_normalized_weighted_spanning_trees():
#     laplacian = nx.laplacian_matrix(graph, weight=weight).toarray()
#     reduced   = laplacian[1:, 1:]
#     eigv2     = scipy.linalg.eigvalsh(reduced); eigv = eigv2[eigv2 > EIG_TH]
#     return exp(sum(log(eigv)) / n)


def get_d_opt(matrix):
    eigv2 = np.linalg.eigvalsh(np.asarray(matrix, dtype=float))
    eigv = eigv2[eigv2 > EIG_TH]
    if eigv.size == 0:
        return 0.0
    return float(np.exp(np.sum(np.log(eigv)) / eigv2.size))


def graph_utility(graph):
    laplacian = nx.laplacian_matrix(graph, weight="weight").toarray()
    reduced = laplacian[1:, 1:]
    if reduced.size == 0:
        return 0.0
    eigv2 = np.linalg.eigvalsh(reduced)
    eigv = eigv2[eigv2 > EIG_TH]
    if eigv.size == 0:
        return 0.0
    return float(np.exp(np.sum(np.log(eigv)) / reduced.shape[1]))


def covariance_matrix(upper_triangle):
    v = [float(x) for x in upper_triangle.split()]
    xx, xy, xz, yy, yz, zz = v[:6]
    return np.array([[xx, xy, xz], [xy, yy, yz], [xz, yz, zz]])


def information_from_covariance(cov):
    """Project convention: information = covariance^-1 (see det_information)."""
    try:
        return np.linalg.inv(cov)
    except np.linalg.LinAlgError:
        return None


def load_snapshot(path):
    data = json.loads(Path(path).read_text())
    nodes = {int(n["id"]): (float(n["x"]), float(n["y"])) for n in data["full_pose_nodes"]}
    edges = []
    for order, e in enumerate(data.get("full_pose_edges", [])):
        s, t = int(e["start"]), int(e["end"])
        cov = covariance_matrix(e["covariance_upper_triangle"])
        edges.append({"source": s, "target": t, "cov": cov,
                      "index": int(e.get("index", order)),
                      "pair": (min(s, t), max(s, t))})
    edges.sort(key=lambda e: e["index"])
    return nodes, edges


def build_graph(nodes, edges, weight_fn=None):
    g = nx.Graph()
    for nid, (x, y) in nodes.items():
        g.add_node(nid, pos=(x, y))
    for e in edges:
        s, t = e["source"], e["target"]
        if s not in nodes or t not in nodes:
            continue
        length = math.hypot(nodes[s][0] - nodes[t][0], nodes[s][1] - nodes[t][1])
        w = weight_fn(e) if weight_fn else 1.0
        # parallel edges collapse in a simple Graph; keep the first (Karto keeps
        # one edge per pair and accumulates covariance, so this matches).
        if g.has_edge(s, t):
            continue
        g.add_edge(s, t, length=length, weight=w)
    return g


def separation_stats(nodes_pre, edges_pre, nodes_after, edges_after):
    """Separation of every NEW edge measured in the graph state at insertion time.

    The exact pre-insertion state is reconstructed by replaying the AFTER graph's
    edges in creation order (`full_pose_edges[].index`); before adding edge i the
    endpoints may already be connected through edges created earlier (for example
    the probe trajectory), which is precisely the cycle this edge closes.
    """
    pre_pairs = {e["pair"] for e in edges_pre}
    g = nx.Graph()
    rows = []
    seen = set()
    for e in edges_after:
        s, t = e["source"], e["target"]
        if s in seen and t in seen and g.has_node(s) and g.has_node(t):
            try:
                hops = nx.shortest_path_length(g, s, t)
                geo = nx.shortest_path_length(g, s, t, weight="length")
                bridges = False
            except nx.NetworkXNoPath:
                hops, geo, bridges = None, None, True
        else:
            hops, geo, bridges = None, None, True
        if e["pair"] not in pre_pairs:
            if s in nodes_after and t in nodes_after:
                edge_len = math.hypot(nodes_after[s][0] - nodes_after[t][0],
                                      nodes_after[s][1] - nodes_after[t][1])
            else:
                edge_len = None
            rows.append({
                "source": s, "target": t, "pair": [min(s, t), max(s, t)],
                "edge_index": e["index"], "edge_length_m": edge_len,
                "geodesic_hops_pre": hops, "geodesic_length_pre_m": geo,
                "cycle_length_m": (geo + edge_len) if (geo is not None and edge_len is not None) else None,
                "bridges_components_pre": bridges,
            })
        # add node/edge for the next iteration (parallel edges collapsed as in Karto)
        for nid in (s, t):
            if nid in nodes_after:
                g.add_node(nid, pos=nodes_after[nid])
        if not g.has_edge(s, t):
            length = math.hypot(nodes_after[s][0] - nodes_after[t][0],
                                nodes_after[s][1] - nodes_after[t][1]) \
                if (s in nodes_after and t in nodes_after) else 1.0
            g.add_edge(s, t, length=length, weight=1.0)
        seen.update((s, t))
    return rows


def utility_ablation(nodes_after, edges_after, target_pairs, history_pairs):
    def weight_of(e):
        info = information_from_covariance(e["cov"])
        return get_d_opt(info) if info is not None else 0.0

    all_edges = edges_after
    without_target = [e for e in all_edges if e["pair"] not in target_pairs]
    without_history = [e for e in all_edges if e["pair"] not in history_pairs]
    u_all = graph_utility(build_graph(nodes_after, all_edges, weight_of))
    u_no_target = graph_utility(build_graph(nodes_after, without_target, weight_of))
    u_no_history = graph_utility(build_graph(nodes_after, without_history, weight_of))
    return {
        "utility_definition": "exp(mean(log(eigenvalues>1e-6))) of reduced cov-weighted Laplacian (utils.py)",
        "U_graph_all": u_all,
        "U_graph_without_target_edges": u_no_target,
        "U_graph_without_all_history_edges": u_no_history,
        "dU_target": u_all - u_no_target,
        "dU_history_all": u_all - u_no_history,
        "dU_target_rel": (u_all - u_no_target) / u_all if u_all else None,
        "dU_history_rel": (u_all - u_no_history) / u_all if u_all else None,
        "n_edges_all": len(all_edges),
        "n_target_edges": len(all_edges) - len(without_target),
        "n_history_edges": len(all_edges) - len(without_history),
    }


def load_ledger_attribution(ledger_path, episode_id):
    """Map (source,target) -> attribution from the edge ledger."""
    attrib = {}
    with open(ledger_path, newline="") as fh:
        for row in csv.DictReader(fh):
            if row.get("episode_id") != episode_id:
                continue
            key = (int(row["source_state_id"]), int(row["target_state_id"]))
            attrib[key] = row
    return attrib


def analyze_episode(episode_dir, ledger_attrib):
    before_nodes, before_edges = load_snapshot(episode_dir / "pose_graph_before.json")
    after_nodes, after_edges = load_snapshot(episode_dir / "pose_graph_after.json")
    rows = separation_stats(before_nodes, before_edges, after_nodes, after_edges)

    target_pairs, wrong_pairs, ordinary_pairs = set(), set(), set()
    for r in rows:
        pair = tuple(r["pair"])
        rec = ledger_attrib.get((r["source"], r["target"])) or ledger_attrib.get(
            (r["target"], r["source"]))
        r["attribution"] = rec["attribution"] if rec else "UNKNOWN_NOT_RECORDED"
        r["creation_provenance"] = rec["creation_provenance"] if rec else "UNKNOWN_NOT_RECORDED"
        r["match_response"] = rec["match_response"] if rec else ""
        if r["attribution"] == "TARGET_ATTRIBUTABLE":
            target_pairs.add(pair)
        elif r["attribution"] == "WRONG_TARGET_HISTORICAL":
            wrong_pairs.add(pair)
        else:
            ordinary_pairs.add(pair)

    history_pairs = target_pairs | wrong_pairs
    ab = utility_ablation(after_nodes, after_edges, target_pairs, history_pairs)

    def stats(subset):
        vals = [r["geodesic_hops_pre"] for r in subset if r["geodesic_hops_pre"] is not None]
        lens = [r["geodesic_length_pre_m"] for r in subset if r["geodesic_length_pre_m"] is not None]
        cycles = [r["cycle_length_m"] for r in subset if r["cycle_length_m"] is not None]
        return {
            "count": len(subset),
            "bridging": sum(1 for r in subset if r["bridges_components_pre"]),
            "hops_pre": {"min": min(vals) if vals else None, "max": max(vals) if vals else None,
                          "values": vals},
            "geodesic_length_pre_m": {"min": min(lens) if lens else None,
                                       "max": max(lens) if lens else None, "values": lens},
            "cycle_length_m": {"min": min(cycles) if cycles else None,
                                "max": max(cycles) if cycles else None, "values": cycles},
        }

    return {
        "before_nodes": len(before_nodes), "before_edges": len(before_edges),
        "after_nodes": len(after_nodes), "after_edges": len(after_edges),
        "new_edges": len(rows),
        "new_edge_rows": rows,
        "by_attribution": {
            "TARGET_ATTRIBUTABLE": stats([r for r in rows if r["attribution"] == "TARGET_ATTRIBUTABLE"]),
            "WRONG_TARGET_HISTORICAL": stats([r for r in rows if r["attribution"] == "WRONG_TARGET_HISTORICAL"]),
            "ORDINARY_RECENT_OR_SEQUENTIAL": stats([r for r in rows if r["attribution"].startswith("ORDINARY")]),
        },
        "utility_ablation": ab,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--suite", required=True, type=Path)
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()
    suite = args.suite
    ledger = suite / "sentinel_edge_ledger.csv"

    result = {"suite": str(suite), "evidence_language": {
        "MEASURED": "computed from saved exact graphs and the paper's own utility",
        "LIMIT": "conditional marginal contribution, not Shapley / not causal effect",
    }, "episodes": {}}

    for ep in sorted(p for p in (suite / "episodes").iterdir() if p.is_dir()):
        attempts = sorted(p for p in ep.iterdir() if p.is_dir() and p.name.startswith("attempt"))
        for att in reversed(attempts):  # newest valid attempt first
            if (att / "pose_graph_after.json").is_file() and (att / "pose_graph_before.json").is_file():
                attrib = load_ledger_attribution(ledger, ep.name) if ledger.is_file() else {}
                result["episodes"][ep.name] = analyze_episode(att, attrib)
                break

    out = args.out or (suite / "graph_separation_ablation_audit.json")
    out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print("wrote", out)
    for name, ep in result["episodes"].items():
        ab = ep["utility_ablation"]
        print(f"\n{name}: {ep['before_nodes']}->{ep['after_nodes']} nodes, "
              f"{ep['before_edges']}->{ep['after_edges']} edges, {ep['new_edges']} new")
        for k, v in ep["by_attribution"].items():
            print(f"  {k}: n={v['count']} bridging={v['bridging']} "
                  f"hops={v['hops_pre']['values']} geodesic_m={[round(x,2) for x in (v['geodesic_length_pre_m']['values'] or [])]}")
        print(f"  U_all={ab['U_graph_all']:.6g} dU_target={ab['dU_target']:.6g} "
              f"(rel {ab['dU_target_rel']:.4f}) dU_history={ab['dU_history_all']:.6g} "
              f"(rel {ab['dU_history_rel']:.4f})")


if __name__ == "__main__":
    sys.exit(main())
