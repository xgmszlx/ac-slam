#!/usr/bin/python3
"""Prospective design and technical-only preregistration for CD-T."""

import csv
import hashlib
import json
import math
import subprocess
from pathlib import Path

import numpy as np

from controlled_branch_suite import atomic_json


ROOT = Path(__file__).resolve().parents[2]
RESULT_ROOT = (ROOT / 'results/realizability_pilot' /
               'p1_context_disentangle_t_20260928')
V14_ROOT = ROOT / 'results/realizability_pilot/p1_v14_confirmatory_20260928'
V14H_ROOT = ROOT / 'results/realizability_pilot/p1_v14_heterogeneity_20260928'
BASE_COMMIT = 'ae8cbb1afd766ddaab03540a7cb7f6dd41aa110d'
PROTOCOL_ID = 'CONTEXT_DISENTANGLEMENT_TECHNICAL_AND_STATISTICAL_CERTIFICATION'
ARMS = ('D0_ZERO', 'D1_THRESHOLD', 'D2_HIGH')
TARGETS = ('target_A', 'target_B')
DOSES = {
    'D0_ZERO': 0.0,
    'D1_THRESHOLD': 1.087946562824985,
    'D2_HIGH': math.pi,
}
N_SCANS = 347
MIN_COMPLETION_MARGIN = 60
YAW_TOLERANCE_RAD = 0.06
D0_YAW_MAX_RAD = 0.03
FINAL_HEADING_TOLERANCE_RAD = 0.04
START_POSITION_TOLERANCE_M = 0.08
START_HEADING_TOLERANCE_RAD = 0.04
DOSE_OVERLAP_MIN_FRACTION = 0.25
DOSE_MEAN_MATCH_TOLERANCE_RAD = 0.06
SAMPLE_SIZES = (4, 6, 8, 10, 12)
EFFECT_FRACTIONS = (1.0, 0.5, 0.25)
VARIANCE_INFLATIONS = (1.0, 1.5, 2.0)
SIMULATION_SEED = 280928
SIMULATION_REPETITIONS = 50000
FUTURE_SEED_POOLS = {
    'target_A': list(range(101001, 101017)),
    'target_B': list(range(102001, 102017)),
}
ARM_ORDERS = {
    'target_A': [
        ['D0_ZERO', 'D1_THRESHOLD', 'D2_HIGH'],
        ['D1_THRESHOLD', 'D2_HIGH', 'D0_ZERO'],
        ['D2_HIGH', 'D0_ZERO', 'D1_THRESHOLD'],
        ['D0_ZERO', 'D2_HIGH', 'D1_THRESHOLD'],
        ['D1_THRESHOLD', 'D0_ZERO', 'D2_HIGH'],
        ['D2_HIGH', 'D1_THRESHOLD', 'D0_ZERO'],
        ['D0_ZERO', 'D1_THRESHOLD', 'D2_HIGH'],
        ['D1_THRESHOLD', 'D2_HIGH', 'D0_ZERO'],
    ],
    'target_B': [
        ['D1_THRESHOLD', 'D0_ZERO', 'D2_HIGH'],
        ['D2_HIGH', 'D1_THRESHOLD', 'D0_ZERO'],
        ['D0_ZERO', 'D2_HIGH', 'D1_THRESHOLD'],
        ['D1_THRESHOLD', 'D2_HIGH', 'D0_ZERO'],
        ['D2_HIGH', 'D0_ZERO', 'D1_THRESHOLD'],
        ['D0_ZERO', 'D1_THRESHOLD', 'D2_HIGH'],
        ['D1_THRESHOLD', 'D0_ZERO', 'D2_HIGH'],
        ['D2_HIGH', 'D1_THRESHOLD', 'D0_ZERO'],
    ],
}


def load_json(path):
    return json.loads(Path(path).read_text())


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def git_head():
    return subprocess.check_output(
        ['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()


def git_branch():
    return subprocess.check_output(
        ['git', 'branch', '--show-current'], cwd=ROOT, text=True).strip()


def remote_head():
    output = subprocess.check_output(
        ['git', 'ls-remote', 'origin', 'refs/heads/research/phase4c-formal'],
        cwd=ROOT, text=True).strip()
    return output.split()[0] if output else None


def git_tree_oid(path):
    relative = Path(path).relative_to(ROOT).as_posix()
    return subprocess.check_output(
        ['git', 'rev-parse', 'HEAD:' + relative], cwd=ROOT,
        text=True).strip()


def path_clean(path):
    relative = Path(path).relative_to(ROOT).as_posix()
    status = subprocess.check_output(
        ['git', 'status', '--porcelain', '--untracked-files=all', '--', relative],
        cwd=ROOT, text=True).strip()
    return not bool(status), status


def frozen_provenance():
    immutable = load_json(V14H_ROOT / 'provenance/v14_immutable_manifest.json')
    v14_failures = []
    for relative, expected in immutable['critical_sha256'].items():
        actual = sha256(V14_ROOT / relative)
        if actual != expected:
            v14_failures.append({'path': relative, 'expected': expected,
                                 'actual': actual})
    v14_clean, v14_status = path_clean(V14_ROOT)
    v14h_clean, v14h_status = path_clean(V14H_ROOT)
    payload = {
        'source_branch': 'research/phase4c-formal',
        'actual_branch_at_freeze': git_branch(),
        'source_head': git_head(),
        'source_remote_head': remote_head(),
        'expected_source_head': BASE_COMMIT,
        'source_worktree_clean_at_task_start': True,
        'v14_tree_oid': git_tree_oid(V14_ROOT),
        'expected_v14_tree_oid': immutable['v14_git_tree_oid'],
        'v14h_tree_oid': git_tree_oid(V14H_ROOT),
        'v14_critical_sha256_checked': len(immutable['critical_sha256']),
        'v14_critical_failures': v14_failures,
        'v14_worktree_clean': v14_clean,
        'v14_worktree_status': v14_status,
        'v14h_worktree_clean': v14h_clean,
        'v14h_worktree_status': v14h_status,
        'heterogeneity_audit_commit': BASE_COMMIT,
    }
    payload['passed'] = bool(
        payload['actual_branch_at_freeze'] == payload['source_branch'] and
        payload['source_head'] == BASE_COMMIT and
        payload['source_remote_head'] == BASE_COMMIT and not v14_failures and
        payload['v14_tree_oid'] == payload['expected_v14_tree_oid'] and
        v14_clean and v14h_clean)
    return payload


def wrap_angle(value):
    return math.atan2(math.sin(value), math.cos(value))


def dose_motion(theta0, arm):
    """Deterministic same-start/same-finish symmetric angular intervention."""
    if arm not in DOSES:
        raise ValueError('unknown controlled dose arm: {}'.format(arm))
    dose = float(DOSES[arm])
    theta0 = float(theta0)
    if dose == 0.0:
        headings = [theta0]
        labels = []
    else:
        headings = [theta0, wrap_angle(theta0 + dose / 2.0), theta0]
        labels = ['dose_peak', 'dose_return']
    cumulative = sum(abs(wrap_angle(right - left))
                     for left, right in zip(headings, headings[1:]))
    return {
        'arm': arm, 'dose_rad': dose, 'theta0_rad': theta0,
        'headings_rad': headings, 'post_start_labels': labels,
        'planned_cumulative_abs_yaw_rad': cumulative,
        'final_heading_rad': headings[-1],
        'rotation_template': 'theta0 -> theta0 + dose/2 -> theta0',
        'direction_semantics': 'positive-outbound_then_negative-return',
    }


def pretreatment_scan_descriptor(record, sectors=12, histogram_bins=10):
    """Compute capture-side descriptors from one strictly pre-action scan."""
    ranges = [float(value) for value in record['ranges']]
    lower, upper = float(record['range_min']), float(record['range_max'])
    valid = [value for value in ranges
             if math.isfinite(value) and lower <= value <= upper]
    normalized = [min(1.0, max(0.0, value / upper)) for value in valid]
    histogram = [0] * histogram_bins
    for value in normalized:
        index = min(histogram_bins - 1, int(value * histogram_bins))
        histogram[index] += 1
    total = float(sum(histogram))
    probabilities = [count / total for count in histogram] if total else []
    entropy = -sum(p * math.log(p) for p in probabilities if p > 0.0)
    filled = [min(upper, max(lower, value)) if math.isfinite(value) else upper
              for value in ranges]
    sector_profile = []
    for sector in range(sectors):
        start = int(len(filled) * sector / sectors)
        end = int(len(filled) * (sector + 1) / sectors)
        values = filled[start:end]
        sector_profile.append(sum(values) / (len(values) * upper)
                              if values else None)
    mirrored = list(reversed(filled))
    symmetry_error = (sum(abs(left - right) / upper
                          for left, right in zip(filled, mirrored)) /
                      len(filled) if filled else None)
    sorted_valid = sorted(valid)

    def quantile(fraction):
        if not sorted_valid:
            return None
        position = fraction * (len(sorted_valid) - 1)
        lower_index = int(math.floor(position))
        upper_index = int(math.ceil(position))
        weight = position - lower_index
        return (sorted_valid[lower_index] * (1.0 - weight) +
                sorted_valid[upper_index] * weight)

    return {
        'strictly_pretreatment': True,
        'scan_stamp': float(record['stamp']),
        'pose_x': float(record['x']), 'pose_y': float(record['y']),
        'pose_yaw': float(record['yaw']),
        'ray_count': len(ranges), 'valid_return_count': len(valid),
        'valid_return_ratio': len(valid) / float(len(ranges)) if ranges else 0.0,
        'normalized_range_histogram_counts': histogram,
        'normalized_angular_range_profile': sector_profile,
        'range_histogram_entropy_nats': entropy,
        'bilateral_symmetry_error': symmetry_error,
        'range_quantiles_m': {
            'q10': quantile(0.10), 'q25': quantile(0.25),
            'q50': quantile(0.50), 'q75': quantile(0.75),
            'q90': quantile(0.90),
        },
        'geometric_openness': (sum(normalized) / len(normalized)
                               if normalized else None),
        'descriptor_affects_backend_input': False,
    }


def interaction_contrast(rows):
    """Direct block-level difference-in-differences interaction."""
    by_target = {target: [] for target in TARGETS}
    for row in rows:
        by_target[row['target']].append(
            float(row['J_D2_HIGH']) - float(row['J_D1_THRESHOLD']))
    if any(not values for values in by_target.values()):
        raise ValueError('both target strata are required')
    means = {target: float(np.mean(values))
             for target, values in by_target.items()}
    return {
        'C_HT_A': means['target_A'], 'C_HT_B': means['target_B'],
        'I_HT': means['target_B'] - means['target_A'],
        'block_contrasts': by_target,
    }


def _v14_primary_values():
    rows = list(csv.DictReader(open(V14_ROOT / 'analysis/primary_block_table.csv')))
    values = {target: [] for target in TARGETS}
    for row in rows:
        values[row['target']].append(float(row['D_sweep']))
    return values


def simulate_sample_size(repetitions=SIMULATION_REPETITIONS,
                         seed=SIMULATION_SEED):
    """Sensitivity only; v14 scale is exploratory and target-confounded."""
    from scipy import stats

    values = _v14_primary_values()
    variance = {target: float(np.var(data, ddof=1))
                for target, data in values.items()}
    observed = float(np.mean(values['target_B']) -
                     np.mean(values['target_A']))
    rng = np.random.default_rng(int(seed))
    output = []
    for effect_fraction in EFFECT_FRACTIONS:
        effect = observed * effect_fraction
        for inflation in VARIANCE_INFLATIONS:
            for n_value in SAMPLE_SIZES:
                a = rng.normal(0.0, math.sqrt(
                    variance['target_A'] * inflation),
                    size=(int(repetitions), n_value))
                b = rng.normal(effect, math.sqrt(
                    variance['target_B'] * inflation),
                    size=(int(repetitions), n_value))
                difference = b.mean(axis=1) - a.mean(axis=1)
                var_a = a.var(axis=1, ddof=1)
                var_b = b.var(axis=1, ddof=1)
                standard_error = np.sqrt(var_a / n_value + var_b / n_value)
                numerator = (var_a / n_value + var_b / n_value) ** 2
                denominator = ((var_a / n_value) ** 2 / (n_value - 1) +
                               (var_b / n_value) ** 2 / (n_value - 1))
                degrees = numerator / denominator
                critical = stats.t.ppf(0.975, degrees)
                half_width = critical * standard_error
                output.append({
                    'audit_label': 'DESIGN_SENSITIVITY_ONLY',
                    'n_blocks_per_target': n_value,
                    'total_blocks': 2 * n_value,
                    'effect_scenario': '{}%_observed_scale'.format(
                        int(100 * effect_fraction)),
                    'effect_fraction': effect_fraction,
                    'true_I_HT': effect,
                    'variance_scenario': '{}x_empirical_variance'.format(
                        inflation),
                    'variance_inflation': inflation,
                    'power_two_sided_positive_direction': float(np.mean(
                        difference - half_width > 0.0)),
                    'sign_stability': float(np.mean(difference > 0.0)),
                    'median_95ci_half_width': float(np.median(half_width)),
                    'p90_95ci_half_width': float(np.quantile(half_width, 0.9)),
                    'simulation_repetitions': int(repetitions),
                    'simulation_seed': int(seed),
                })
    return output, {
        'observed_I_HT_scale': observed,
        'target_A_empirical_variance': variance['target_A'],
        'target_B_empirical_variance': variance['target_B'],
        'source_primary_table_sha256': sha256(
            V14_ROOT / 'analysis/primary_block_table.csv'),
        'warning': ('v14 scale is exploratory, target-confounded, and used '
                    'only for design sensitivity'),
    }


def sample_size_recommendation(rows, source):
    def lookup(n_value, fraction, inflation):
        return next(row for row in rows
                    if row['n_blocks_per_target'] == n_value and
                    row['effect_fraction'] == fraction and
                    row['variance_inflation'] == inflation)

    eligible = []
    for n_value in SAMPLE_SIZES:
        observed = lookup(n_value, 1.0, 2.0)
        half = lookup(n_value, 0.5, 2.0)
        quarter = lookup(n_value, 0.25, 2.0)
        checks = {
            'observed_scale_2x_power_at_least_0_95':
                observed['power_two_sided_positive_direction'] >= 0.95,
            'half_scale_2x_power_at_least_0_80':
                half['power_two_sided_positive_direction'] >= 0.80,
            'quarter_scale_2x_sign_stability_at_least_0_95':
                quarter['sign_stability'] >= 0.95,
        }
        if all(checks.values()):
            eligible.append((n_value, checks))
    selected = eligible[0][0] if eligible else max(SAMPLE_SIZES)
    return {
        'status': 'FROZEN_DESIGN_RECOMMENDATION',
        'selected_blocks_per_target': selected,
        'total_selected_blocks': 2 * selected,
        'selection_rule': ('smallest candidate meeting all three conservative '
                           '2x-variance criteria'),
        'selection_checks': (eligible[0][1] if eligible else
                             {'no_candidate_met_all_criteria': True}),
        'candidate_sizes': list(SAMPLE_SIZES),
        'source': source,
        'qualification_pool_multiplier': 2.0,
        'candidate_seed_pools': FUTURE_SEED_POOLS,
        'first_N_eligible_in_frozen_order': True,
        'outcome_driven_replacement_allowed': False,
    }


def _write_csv(path, rows):
    rows = list(rows)
    fields = list(rows[0]) if rows else []
    with open(path, 'w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def relevant_code_files():
    return [ROOT / name for name in (
        'tools/realizability_pilot/context_disentangle_protocol.py',
        'tools/realizability_pilot/context_disentangle_capture.py',
        'tools/realizability_pilot/context_disentangle_technical.py',
        'tools/realizability_pilot/test_context_disentangle.py',
        'tools/realizability_pilot/controlled_probe_capture.py',
        'tools/realizability_pilot/fixed_scan_capture.py')]


def dose_definition():
    return {
        'protocol_id': PROTOCOL_ID,
        'intervention_name': 'STANDARDIZED_CONTROLLED_ANGULAR_DOSE',
        'not_a1_a3_a2_replication': True,
        'arms': {arm: dose_motion(0.0, arm) for arm in ARMS},
        'common_geometry': {
            'start': 'same anchor x, y, theta0 within each block',
            'finish': 'same anchor x, y, theta0 within each block',
            'template': 'theta0 -> theta0 + dose/2 -> theta0',
            'fixed_direction': ('positive outbound and negative return for every '
                                'target/block/dose; no direction factor'),
        },
        'controller_lock': {
            'max_angular_velocity_rad_s': 0.65,
            'proportional_gain': 1.8,
            'heading_tolerance_rad': 0.018,
            'stable_cycles': 3,
            'controller_period_s': 0.05,
            'zero_twist_hold': True,
            'acceleration_semantics': 'same unclipped proportional law for D1/D2',
            'only_planned_difference': 'cumulative angular dose',
        },
        'dose_sources': {
            'D1_THRESHOLD': ('v14 A3 median planned post-arrival cumulative '
                             'angular path'),
            'D2_HIGH': ('v14 A2 median planned post-arrival cumulative angular '
                        'path, standardized to pi'),
        },
    }


def statistical_analysis_plan(selected_n):
    return {
        'status': 'FUTURE_ANALYSIS_PLAN_FROZEN_DESIGN_ONLY',
        'statistical_unit': 'canonical-history block',
        'design': {
            'dose_factor': 'within-block repeated measure',
            'context_factor': 'between-context stratum Target A/B',
            'blocks_per_target': selected_n,
            'independent_sample_count': 2 * selected_n,
            'branch_count_not_independent_n': 3 * 2 * selected_n,
        },
        'primary_estimand': {
            'C_HT_block': 'J_T(D2_HIGH)-J_T(D1_THRESHOLD)',
            'C_HT_A': 'mean Target-A block C_HT',
            'C_HT_B': 'mean Target-B block C_HT',
            'I_HT': 'C_HT_B-C_HT_A',
            'co_primary_contrasts': [],
        },
        'secondary_scientific_contrasts': {
            'C_T0': 'J_T(D1_THRESHOLD)-J_T(D0_ZERO)',
            'C_H0': 'J_T(D2_HIGH)-J_T(D0_ZERO)',
            'target_interactions': 'B-minus-A for C_T0 and C_H0',
        },
        'mechanistic_secondary': {
            'per_branch': [
                'accepted_keyscans', 'E_T', 'E_N',
                'historical_factor_total', 'historical_endpoint_set',
                'endpoint_novelty', 'endpoint_loss', 'insertion_geodesic',
                'hops', 'cycle_length', 'information_eigenvalues',
                'matcher_response', 'provenance_family'],
            'H_HT': ('HistoricalFactors(D2_HIGH)-'
                     'HistoricalFactors(D1_THRESHOLD)'),
            'I_HIST_HT': 'mean_B(H_HT)-mean_A(H_HT)',
            'causal_mediation_claim_allowed': False,
        },
        'inference': {
            'primary': ('block bootstrap or randomization/permutation respecting '
                        'within-block pairing and target strata'),
            'report': ['I_HT point estimate', '95% interval',
                       'target-stratified paired contrasts', 'raw block points'],
            'mixed_model': 'auxiliary only',
            'branch_pseudoreplication_forbidden': True,
        },
    }


def prepare():
    provenance = frozen_provenance()
    if not provenance['passed']:
        raise RuntimeError('frozen provenance verification failed')
    for directory in ('preregistration', 'design', 'technical', 'decision'):
        (RESULT_ROOT / directory).mkdir(parents=True, exist_ok=True)
    if any(RESULT_ROOT.iterdir()):
        existing = [path for path in RESULT_ROOT.rglob('*') if path.is_file()]
        if existing:
            raise RuntimeError('refusing to overwrite existing CD-T outputs')
    rows, source = simulate_sample_size()
    recommendation = sample_size_recommendation(rows, source)
    dose = dose_definition()
    analysis = statistical_analysis_plan(
        recommendation['selected_blocks_per_target'])
    code_hashes = {str(path.relative_to(ROOT)): sha256(path)
                   for path in relevant_code_files()}
    protocol = {
        'protocol_id': PROTOCOL_ID,
        'scientific_role': 'TECHNICAL_AND_STATISTICAL_CERTIFICATION_ONLY',
        'scientific_experiment_started': False,
        'scientific_backend_endpoint_allowed': False,
        'formal_scientific_gate_unchanged': 'V14_PROSPECTIVE_NO_SUPPORT',
        'universal_broad_sweep_hypothesis': 'STOPPED',
        'heterogeneity_direction': 'MULTIFACTOR_INTERACTION_CANDIDATE',
        'base_commit': BASE_COMMIT,
        'provenance': provenance,
        'code_hashes': code_hashes,
        'code_bundle_sha256': hashlib.sha256(json.dumps(
            code_hashes, sort_keys=True,
            separators=(',', ':')).encode()).hexdigest(),
        'arms': list(ARMS), 'dose_definition': dose,
        'technical_geometry_source': ('frozen v14 Target A/B H1-H4 action '
                                      'specifications; no backend replay'),
        'fixed_sensing_exposure': {
            'candidate_N': N_SCANS,
            'minimum_completion_margin': MIN_COMPLETION_MARGIN,
            'exact_first_N_required': True,
            'automatic_N_change_allowed': False,
        },
        'technical_branches': 24,
        'future_repeated_measures': True,
        'future_arm_orders': ARM_ORDERS,
        'future_seed_pools': FUTURE_SEED_POOLS,
        'manipulation_checks': {
            'yaw_tolerance_rad': YAW_TOLERANCE_RAD,
            'D0_max_yaw_rad': D0_YAW_MAX_RAD,
            'final_heading_tolerance_rad': FINAL_HEADING_TOLERANCE_RAD,
            'strict_dose_monotonicity': True,
            'target_dose_overlap_min_fraction': DOSE_OVERLAP_MIN_FRACTION,
            'target_mean_dose_match_tolerance_rad':
                DOSE_MEAN_MATCH_TOLERANCE_RAD,
            'completion_scan_raw_range_overlap_required': True,
        },
        'pre_treatment_logging': {
            'capture_side_only': True, 'backend_input_changed': False,
            'laser_descriptors': [
                'range_histogram', 'angular_range_profile',
                'valid_return_ratio', 'range_entropy', 'bilateral_symmetry',
                'range_quantiles', 'geometric_openness'],
            'pregraph_descriptors_future_only': [
                'local_degree', 'local_cycle_rank', 'local_connectivity'],
        },
        'primary_estimand': analysis['primary_estimand'],
        'sample_size_recommendation': recommendation,
        'stop_rule': ('no scientific collection until technical gate is '
                      'CONTEXT_DISENTANGLEMENT_TECHNICALLY_READY'),
    }
    atomic_json(RESULT_ROOT / 'provenance_at_freeze.json', provenance)
    atomic_json(RESULT_ROOT / 'design/dose_definition.json', dose)
    _write_csv(RESULT_ROOT / 'design/sample_size_sensitivity.csv', rows)
    atomic_json(RESULT_ROOT / 'design/sample_size_recommendation.json',
                recommendation)
    atomic_json(RESULT_ROOT / 'design/future_statistical_analysis_plan.json',
                analysis)
    atomic_json(RESULT_ROOT / 'preregistration/CDT_protocol.json', protocol)
    return {
        'status': 'CDT_PREREGISTERED_TECHNICAL_ONLY',
        'protocol_sha256': sha256(
            RESULT_ROOT / 'preregistration/CDT_protocol.json'),
        'selected_blocks_per_target':
            recommendation['selected_blocks_per_target'],
        'technical_branches_planned': 24,
        'scientific_endpoint_allowed': False,
    }


if __name__ == '__main__':
    print(json.dumps(prepare(), indent=2, sort_keys=True))
