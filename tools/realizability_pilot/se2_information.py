#!/usr/bin/python3
"""SE(2) pose-graph linearised information and marginal-covariance tooling.

Formulation (standard first-order pose-graph linearisation):

* every graph constraint (odometry-like or loop-closing) contributes
  ``J^T Omega J`` to the information matrix ``Lambda`` of the interleaved full
  state ``[x_0, y_0, theta_0, ..., x_n, y_n, theta_n]``;
* ``Omega`` is the 3x3 inverse of the constraint covariance published per edge by
  the mapper's full pose-graph observer;
* ``J`` is the Jacobian of the relative-pose error with respect to the source and
  target poses, evaluated at the current corrected estimate (no measurement value
  enters ``J``, which is why the ablation needs no raw measurements);
* legacy analyses in this repository expose a Moore-Penrose utility.  The v13
  primary estimator does **not** use it: v13 fixes the first pose, inverts the
  reduced information matrix, and extracts the joint marginal covariance of
  the five frozen target poses at the same local linearisation point.  This is
  a local linear-Gaussian covariance, not an exact nonlinear posterior.

Nothing in this module feeds back into the running system: it is a read-only
analysis of recorded snapshots.
"""

import math

import numpy as np

EIGENVALUE_TOLERANCE = 1e-9


def covariance_from_upper_triangle(text):
    """Expand the mapper's 6-element upper triangle into a 3x3 covariance."""
    values = [float(value) for value in str(text).split()]
    if len(values) != 6:
        raise ValueError(
            'expected 6 upper-triangle values, got {}'.format(len(values)))
    matrix = np.zeros((3, 3))
    matrix[0, 0] = values[0]
    matrix[0, 1] = matrix[1, 0] = values[1]
    matrix[0, 2] = matrix[2, 0] = values[2]
    matrix[1, 1] = values[3]
    matrix[1, 2] = matrix[2, 1] = values[4]
    matrix[2, 2] = values[5]
    return matrix


def safe_information(covariance, regularisation=1e-9):
    """Invert a covariance with symmetrisation and eigenvalue clipping."""
    symmetric = 0.5 * (covariance + covariance.T)
    eigenvalues, eigenvectors = np.linalg.eigh(symmetric)
    floor = max(regularisation, float(np.max(np.abs(eigenvalues))) * 1e-12)
    clipped = np.clip(eigenvalues, floor, None)
    inverse = (eigenvectors / clipped) @ eigenvectors.T
    return 0.5 * (inverse + inverse.T)


def relative_pose(source, target):
    """Relative pose of ``target`` in the frame of ``source`` (x, y, theta)."""
    cosine = math.cos(float(source[2]))
    sine = math.sin(float(source[2]))
    dx = float(target[0]) - float(source[0])
    dy = float(target[1]) - float(source[1])
    return (
        cosine * dx + sine * dy,
        -sine * dx + cosine * dy,
        math.atan2(math.sin(float(target[2]) - float(source[2])),
                   math.cos(float(target[2]) - float(source[2]))),
    )


def edge_jacobian(source, target):
    """3x6 Jacobian of the relative-pose error at the current estimate.

    Error definition::

        e = [ R(theta_i)^T (p_j - p_i) ; theta_j - theta_i ]

    Missing the measured relative pose only shifts the residual, not the
    Jacobian, so the linearised information is exact for this estimate.
    """
    theta = float(source[2])
    cosine = math.cos(theta)
    sine = math.sin(theta)
    dx = float(target[0]) - float(source[0])
    dy = float(target[1]) - float(source[1])
    rotation_t = np.array([[cosine, sine], [-sine, cosine]])
    rotation_derivative_t = np.array([[-sine, cosine], [-cosine, -sine]])
    jacobian = np.zeros((3, 6))
    jacobian[0:2, 0:2] = -rotation_t
    jacobian[0:2, 2] = rotation_derivative_t @ np.array([dx, dy])
    jacobian[0:2, 3:5] = rotation_t
    jacobian[2, 2] = -1.0
    jacobian[2, 5] = 1.0
    return jacobian


def build_information(node_ids, edges, excluded_pairs=()):
    """Assemble Lambda for the node ordering given by ``node_ids``.

    ``edges`` is an iterable of dicts with ``start``, ``end`` and
    ``covariance_upper_triangle``.  Edges whose unordered endpoint pair is in
    ``excluded_pairs`` are skipped (that is the ablation mechanism).
    """
    index_of = {int(node_id): position for position, node_id in enumerate(node_ids)}
    size = 3 * len(node_ids)
    information = np.zeros((size, size))
    contributors = 0
    rejected = []
    excluded = {tuple(sorted(pair)) for pair in excluded_pairs}
    for edge in edges:
        start = int(edge['start'])
        end = int(edge['end'])
        if start not in index_of or end not in index_of:
            continue
        if tuple(sorted((start, end))) in excluded:
            continue
        try:
            covariance = covariance_from_upper_triangle(
                edge['covariance_upper_triangle'])
            omega = safe_information(covariance)
        except Exception as exc:  # pragma: no cover - defensive
            rejected.append((start, end, str(exc)))
            continue
        jacobian = edge_jacobian(
            [edge['source_pose'][0], edge['source_pose'][1], edge['source_pose'][2]],
            [edge['target_pose'][0], edge['target_pose'][1], edge['target_pose'][2]],
        )
        i = index_of[start]
        j = index_of[end]
        i_slice = slice(3 * i, 3 * i + 3)
        j_slice = slice(3 * j, 3 * j + 3)
        information[i_slice, i_slice] += jacobian[:, 0:3].T @ omega @ jacobian[:, 0:3]
        information[i_slice, j_slice] += jacobian[:, 0:3].T @ omega @ jacobian[:, 3:6]
        information[j_slice, i_slice] += jacobian[:, 3:6].T @ omega @ jacobian[:, 0:3]
        information[j_slice, j_slice] += jacobian[:, 3:6].T @ omega @ jacobian[:, 3:6]
        contributors += 1
    information = 0.5 * (information + information.T)
    return information, contributors, rejected


def pseudoinverse_information(information):
    """Moore-Penrose pseudoinverse with an explicit null-space report."""
    symmetric = 0.5 * (information + information.T)
    eigenvalues, eigenvectors = np.linalg.eigh(symmetric)
    largest = float(np.max(np.abs(eigenvalues))) if eigenvalues.size else 0.0
    tolerance = max(largest * 1e-10, 1e-12)
    positive = eigenvalues > tolerance
    inverse = np.zeros_like(symmetric)
    if positive.any():
        inverse = (eigenvectors[:, positive] / eigenvalues[positive]) \
            @ eigenvectors[:, positive].T
    return 0.5 * (inverse + inverse.T), int((~positive).sum()), eigenvalues


def fixed_root_reduced_information(information, root_position=0,
                                   eigenvalue_tolerance=1e-10):
    """Return an invertible reduced Hessian after fixing one SE(2) pose.

    Raises ``numpy.linalg.LinAlgError`` for a disconnected/singular graph.  The
    strict failure is intentional: v13 must not conceal missing connectivity
    with a pseudoinverse.
    """
    information = 0.5 * (information + information.T)
    node_count = information.shape[0] // 3
    if information.shape != (3 * node_count, 3 * node_count):
        raise ValueError('information shape is not an SE(2) pose graph')
    if root_position < 0 or root_position >= node_count:
        raise IndexError('root position is outside the pose graph')
    removed = set(range(3 * root_position, 3 * root_position + 3))
    kept = [index for index in range(information.shape[0])
            if index not in removed]
    reduced = information[np.ix_(kept, kept)]
    eigenvalues = np.linalg.eigvalsh(reduced)
    scale = max(float(np.max(np.abs(eigenvalues))), 1.0)
    if eigenvalues.size and float(np.min(eigenvalues)) <= (
            eigenvalue_tolerance * scale):
        raise np.linalg.LinAlgError(
            'fixed-root information is not positive definite')
    return reduced, kept, eigenvalues


def fixed_root_covariance(information, root_position=0):
    """Invert the fixed-root reduced Hessian and report retained indices."""
    reduced, kept, eigenvalues = fixed_root_reduced_information(
        information, root_position=root_position)
    covariance = np.linalg.inv(reduced)
    covariance = 0.5 * (covariance + covariance.T)
    return covariance, kept, eigenvalues


def anchored_information(information, root_position=0):
    """Construct a full, directly invertible hard-anchor representation.

    Root cross terms are zeroed and the root block is set to identity.  The
    non-root inverse block is exactly the inverse of the reduced fixed-root
    information matrix; the artificial root block is never an uncertainty
    estimate and must not be included in a v13 target subset.
    """
    anchored = 0.5 * (information + information.T)
    anchored = anchored.copy()
    indices = list(range(3 * root_position, 3 * root_position + 3))
    anchored[indices, :] = 0.0
    anchored[:, indices] = 0.0
    anchored[np.ix_(indices, indices)] = np.eye(3)
    return anchored


def fixed_root_joint_marginal(information, target_positions,
                              root_position=0):
    """Joint covariance for ordered target poses under a fixed-root gauge."""
    targets = [int(value) for value in target_positions]
    if root_position in targets:
        raise ValueError('the fixed root cannot be a stochastic target pose')
    covariance, kept, _ = fixed_root_covariance(
        information, root_position=root_position)
    reduced_index = {full: reduced for reduced, full in enumerate(kept)}
    selected = []
    for position in targets:
        selected.extend(reduced_index[index]
                        for index in range(3 * position, 3 * position + 3))
    return covariance[np.ix_(selected, selected)]


def v13_target_information_score(information, target_positions,
                                 root_position=0):
    """Compute v13 primary ``J_T = -logdet(Sigma_T) / (3*|T|)``."""
    marginal = fixed_root_joint_marginal(
        information, target_positions, root_position=root_position)
    sign, logdet = np.linalg.slogdet(marginal)
    if sign <= 0 or not np.isfinite(logdet):
        raise np.linalg.LinAlgError('target marginal is not positive definite')
    return -float(logdet) / marginal.shape[0], marginal


def block_metrics(marginal, node_position):
    """Trace, log-determinant and finite-ness of a 3x3 covariance block."""
    block = marginal[3 * node_position:3 * node_position + 3,
                     3 * node_position:3 * node_position + 3]
    block = 0.5 * (block + block.T)
    eigenvalues = np.linalg.eigvalsh(block)
    trace = float(np.sum(eigenvalues))
    positive = eigenvalues[eigenvalues > 0.0]
    logdet = float(np.sum(np.log(positive))) if positive.size == 3 else None
    return {
        'trace': trace,
        'logdet': logdet,
        'eigenvalues': [float(value) for value in eigenvalues],
        'finite': bool(np.all(np.isfinite(block))),
        'positive_semidefinite': bool(np.all(eigenvalues >= -1e-12)),
    }


def group_block_metrics(marginal, positions):
    """Aggregate block metrics over a set of node positions."""
    blocks = [block_metrics(marginal, position) for position in sorted(positions)]
    traces = [block['trace'] for block in blocks]
    logdets = [block['logdet'] for block in blocks if block['logdet'] is not None]
    return {
        'node_count': len(blocks),
        'trace_mean': float(np.mean(traces)) if traces else None,
        'trace_median': float(np.median(traces)) if traces else None,
        'trace_max': float(np.max(traces)) if traces else None,
        'logdet_mean': float(np.mean(logdets)) if logdets else None,
        'logdet_sum': float(np.sum(logdets)) if logdets else None,
        'all_finite': bool(all(block['finite'] for block in blocks)),
        'all_psd': bool(all(block['positive_semidefinite'] for block in blocks)),
    }


def d_opt(information):
    """D-optimality scalar of a symmetric information matrix.

    ``exp(mean(log(eigenvalues)))`` over numerically non-zero eigenvalues, which
    is the geometric-mean generalisation of ``det(Lambda)^(1/n)`` used by the
    project's existing Information/D-opt utilities.
    """
    symmetric = 0.5 * (information + information.T)
    eigenvalues = np.linalg.eigvalsh(symmetric)
    largest = float(np.max(np.abs(eigenvalues))) if eigenvalues.size else 0.0
    positive = eigenvalues[eigenvalues > max(largest * 1e-10, 1e-12)]
    if positive.size == 0:
        return 0.0
    return float(np.exp(np.mean(np.log(positive))))


def constraint_d_opt(covariance):
    """D-opt of one constraint's own 3x3 information matrix."""
    information = safe_information(covariance)
    return d_opt(information)
