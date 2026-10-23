#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Figures for the archived consistency results. Reads results/per_frame.csv only.

Assistant-authored, 2026-10-21. English labels to avoid CJK font dependence.

Usage: python3 code/plot_figures.py
"""
import csv
import os
from collections import defaultdict

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
FIGS = os.path.join(ROOT, 'figures')

CHI2_3_MEDIAN = 2.3660  # median of chi-square with 3 dof


def load():
    rows = defaultdict(list)
    with open(os.path.join(ROOT, 'results', 'per_frame.csv')) as f:
        for r in csv.DictReader(f):
            rows[r['condition']].append(r)
    return rows


def fig_tail(rows):
    fig, ax = plt.subplots(1, 2, figsize=(11, 4.2))
    for scene, color in (('static_0', 'tab:blue'), ('lt_changes_0', 'tab:red')):
        key = '%s_sigma0.02' % scene
        nees = np.sort(np.asarray([float(r['nees']) for r in rows[key]]))
        y = np.arange(1, len(nees) + 1) / len(nees)
        ax[0].plot(np.maximum(nees, 1e-3), y, color=color,
                   label='%s, sigma=0.02 m (n=%d)' % (scene, len(nees)))
    ax[0].set_xscale('log')
    ax[0].set_xlabel('NEES (expected median 2.37 for 3 dof)')
    ax[0].set_ylabel('empirical CDF')
    ax[0].axvline(2.3660, color='k', ls='--', lw=1, label='chi2_3 median')
    ax[0].axvline(3.0, color='k', ls=':', lw=1, label='mean of chi2_3 = 3')
    ax[0].set_title('Row-level NEES CDF, nominal range noise')
    ax[0].legend(fontsize=7, loc='lower right')
    ax[0].grid(alpha=0.3)

    for scene, color in (('static_0', 'tab:blue'), ('lt_changes_0', 'tab:red')):
        for sigma, ls in ((0.02, '-'), (0.04, '--'), (0.06, ':')):
            key = '%s_sigma%.2f' % (scene, sigma)
            nees = np.asarray([float(r['nees']) for r in rows[key]])
            ax[1].scatter(sigma, np.median(nees), color=color, marker='o')
            ax[1].annotate('%s' % scene, (sigma, np.median(nees)),
                           textcoords='offset points', xytext=(6, 2), fontsize=7,
                           color=color)
    s = np.linspace(0.018, 0.065, 50)
    ax[1].plot(s, 3.0 * (0.02 / s) ** 2, 'k--', lw=1,
               label='exact 1/sigma^2 scaling through (0.02, 3)')
    ax[1].axhline(3.0, color='k', ls=':', lw=1)
    ax[1].set_yscale('log')
    ax[1].set_xlabel('assumed range noise sigma (m)')
    ax[1].set_ylabel('median NEES of the rows')
    ax[1].set_title('NEES follows 1/sigma^2 exactly -> one free scale')
    ax[1].legend(fontsize=7)
    ax[1].grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(os.path.join(FIGS, '01_nees_distribution_and_scaling.png'), dpi=140)
    plt.close(fig)


def fig_tail_geometry(rows):
    fig, ax = plt.subplots(1, 2, figsize=(11, 4.2), sharey=True)
    for i, (scene, metric, title) in enumerate((
            ('static_0', 'gamma_lmin_over_lmax_mixed_units',
             'mixed-unit lmin/lmax (as previously reported)'),
            ('static_0', 'gamma_xy_translation_only',
             'translation-only lmin/lmax (unit invariant)'))):
        for sc, color in (('static_0', 'tab:blue'), ('lt_changes_0', 'tab:red')):
            key = '%s_sigma0.02' % sc
            g = np.asarray([float(r[metric]) for r in rows[key]])
            n = np.asarray([float(r['nees']) for r in rows[key]])
            ax[i].scatter(g, np.maximum(n, 1e-2), s=8, alpha=0.6, color=color,
                          label=sc)
        ax[i].set_xlabel(metric)
        ax[i].set_yscale('log')
        ax[i].set_title(title, fontsize=9)
        ax[i].grid(alpha=0.3)
        ax[i].legend(fontsize=7)
    ax[0].set_ylabel('NEES (log)')
    fig.suptitle('Tail vs geometry: the split only survives the unit-invariant '
                 'metric on lt_changes_0', fontsize=9)
    fig.tight_layout(rect=(0, 0, 1, 0.94))
    fig.savefig(os.path.join(FIGS, '02_tail_versus_geometry.png'), dpi=140)
    plt.close(fig)


def fig_errors(rows):
    fig, ax = plt.subplots(1, 3, figsize=(12, 3.6))
    labels = ['x (m)', 'y (m)', 'theta (rad)']
    for j, lab in enumerate(labels):
        for sc, color in (('static_0', 'tab:blue'), ('lt_changes_0', 'tab:red')):
            key = '%s_sigma0.02' % sc
            e = np.asarray([float(r[['e_x', 'e_y', 'e_theta'][j]]) for r in rows[key]])
            ax[j].hist(e, bins=40, histtype='step', color=color, label=sc)
        ax[j].set_title('error component: %s' % lab, fontsize=9)
        ax[j].grid(alpha=0.3)
        if j == 0:
            ax[j].set_ylabel('rows')
            ax[j].legend(fontsize=7)
    fig.tight_layout()
    fig.savefig(os.path.join(FIGS, '03_error_components.png'), dpi=140)
    plt.close(fig)


def fig_normalized_tail(rows):
    """The scale-free view: NEES divided by its own median must follow chi2_3.

    For k=3 dof, survival of chi2 = erfc(sqrt(x/2)) + sqrt(2x/pi) exp(-x/2).
    """
    import math
    erfc = np.vectorize(math.erfc)
    fig, ax = plt.subplots(figsize=(6.6, 4.6))
    x = np.logspace(-0.5, 4.4, 400)
    surv = erfc(np.sqrt(x / 2.0)) + np.sqrt(2 * x / np.pi) * np.exp(-x / 2.0)
    ax.plot(x, surv, 'k--', lw=1.4, label='chi2_3 (covariance correct up to any scale)')
    for scene, color in (('static_0', 'tab:blue'), ('lt_changes_0', 'tab:red')):
        key = '%s_sigma0.02' % scene
        nees = np.asarray([float(r['nees']) for r in rows[key]])
        u = np.sort(nees / np.median(nees))
        y = 1.0 - np.arange(len(u)) / len(u)
        ax.plot(u, y, color=color, lw=1.4,
                label='%s (%d rows / %d frames)' % (
                    scene, len(u), len({r['frame'] for r in rows[key]})))
    ax.set_xscale('log')
    ax.set_yscale('log')
    ax.set_xlabel('NEES divided by its own median  (scale free)')
    ax.set_ylabel('fraction of rows exceeding')
    ax.set_title('Isotropic variance inflation cannot repair this shape', fontsize=9)
    ax.legend(fontsize=7)
    ax.grid(alpha=0.3, which='both')
    fig.tight_layout()
    fig.savefig(os.path.join(FIGS, '04_scale_free_tail.png'), dpi=140)
    plt.close(fig)


def main():
    os.makedirs(FIGS, exist_ok=True)
    rows = load()
    fig_tail(rows)
    fig_tail_geometry(rows)
    fig_errors(rows)
    fig_normalized_tail(rows)
    print('wrote 4 figures to', FIGS)


if __name__ == '__main__':
    main()
