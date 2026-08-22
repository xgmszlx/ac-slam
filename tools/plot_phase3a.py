#!/usr/bin/python3
"""Phase 3A plots (recommended set). Uses only aggregate CSVs; no new runs."""

import csv
import math
from collections import defaultdict
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
ANALYSIS = ROOT / 'results' / 'phase3a' / 'analysis'
AGG = ROOT / 'results' / 'phase3a' / 'aggregate'


def num(v):
    if v is None or v == '' or v == 'None':
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def plot_scatter_by_outcome(features, xkey, ykey, xlabel, ylabel, fname, title=None):
    groups = defaultdict(list)
    for r in features:
        x, y = num(r.get(xkey)), num(r.get(ykey))
        if x is None or y is None:
            continue
        groups[r['failure_subclass']].append((x, y))
    fig, ax = plt.subplots(figsize=(6, 4))
    colors = {'C3': '#d1495b', 'D1': '#2e86ab', 'S': '#1b9e77'}
    for sub, pts in sorted(groups.items()):
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        ax.scatter(xs, ys, label='{} (n={})'.format(sub, len(pts)),
                   color=colors.get(sub, '#888'), s=55, alpha=0.85, edgecolor='k', linewidth=0.4)
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    ax.set_title(title or '{} vs {}'.format(ykey, xkey))
    ax.legend()
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(AGG / fname, dpi=130)
    plt.close(fig)


def main():
    AGG.mkdir(parents=True, exist_ok=True)
    features = list(csv.DictReader(open(ANALYSIS / 'loop_realization_features.csv')))

    # 1. chain persistence by outcome
    plot_scatter_by_outcome(
        features, 'fraction_keyscans_valid_chain', 'best_coarse_response',
        'valid-chain fraction (keyscans with chain>=4)', 'best coarse response',
        'chain_persistence_by_outcome.png',
        'Chain persistence vs coarse response (21 Phase 2C loops)')

    # 2. coarse response by outcome
    plot_scatter_by_outcome(
        features, 'history_path_length_m', 'best_coarse_response',
        'history path length (m)', 'best coarse response',
        'coarse_response_by_outcome.png',
        'Coarse response vs history-path coverage')

    # 3. continuous overlap by outcome
    plot_scatter_by_outcome(
        features, 'cont_overlap_1_0m_samples', 'fraction_keyscans_valid_chain',
        'continuous overlap <=1 m (samples)', 'valid-chain fraction',
        'continuous_overlap_by_outcome.png',
        'Continuous overlap vs chain persistence')

    # 4. yaw consistency by outcome
    plot_scatter_by_outcome(
        features, 'yaw_diff_median_rad', 'best_coarse_response',
        'median yaw diff to history (rad)', 'best coarse response',
        'yaw_consistency_by_outcome.png',
        'Orientation consistency vs coarse response')

    # 5. oracle before/after (requires oracle_results.csv)
    or_path = AGG / 'oracle_results.csv'
    if or_path.is_file():
        rows = list(csv.DictReader(open(or_path)))
        fig, axes = plt.subplots(1, 2, figsize=(10, 4))
        # valid-chain fraction before vs after
        ax = axes[0]
        for r in rows:
            if r.get('status') != 'OK':
                continue
            x, y = num(r.get('v0_fraction_valid_chain')), num(r.get('fraction_valid_chain'))
            if x is None or y is None:
                continue
            ax.scatter(x, y, s=70, alpha=0.85, edgecolor='k', linewidth=0.4,
                       label='v{}'.format(r.get('loop_vertex')))
        lim = [0, 1]
        ax.plot(lim, lim, 'k--', alpha=0.4)
        ax.set_xlim(lim)
        ax.set_ylim(lim)
        ax.set_xlabel('V0 valid-chain fraction')
        ax.set_ylabel('V1 valid-chain fraction')
        ax.set_title('Chain persistence: V0 vs V1')
        ax.grid(alpha=0.3)
        # best coarse before vs after
        ax = axes[1]
        for r in rows:
            if r.get('status') != 'OK':
                continue
            x, y = num(r.get('v0_best_coarse')), num(r.get('best_coarse'))
            if x is None or y is None:
                continue
            ax.scatter(x, y, s=70, alpha=0.85, edgecolor='k', linewidth=0.4,
                       label='v{}'.format(r.get('loop_vertex')))
        lim = [0, 1]
        ax.plot(lim, lim, 'k--', alpha=0.4)
        ax.axhline(0.6, color='r', ls=':', alpha=0.5)
        ax.axvline(0.6, color='r', ls=':', alpha=0.5)
        ax.set_xlim(lim)
        ax.set_ylim(lim)
        ax.set_xlabel('V0 best coarse response')
        ax.set_ylabel('V1 best coarse response')
        ax.set_title('Coarse response: V0 vs V1')
        ax.grid(alpha=0.3)
        fig.tight_layout()
        fig.savefig(AGG / 'oracle_before_after.png', dpi=130)
        plt.close(fig)

    print('plots written to', AGG)


if __name__ == '__main__':
    main()
