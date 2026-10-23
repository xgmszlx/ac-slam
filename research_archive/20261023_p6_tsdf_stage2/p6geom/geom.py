#!/usr/bin/env python3
"""Depth warping between camera views, with a correct z-buffer.

Frame conventions (the bug that this module exists to prevent):
  Twc[k] maps a point from camera k's frame to the world: P_w = Twc[k] @ P_cam_k
  The GT trajectory of TUM RGB-D gives exactly this (camera-to-world).

  v1 of tsdf_stage2_ab.py computed  T_rel = inv(Twc_curr) @ Twc_prev  (a
  current<-previous *camera frame* transform) and then applied it to points that had
  already been taken to the WORLD frame. That is a frame mismatch: T_rel is only valid
  acting on previous-camera coordinates. Correct is either
      P_curr = inv(Twc_curr) @ P_prev_cam_applied_...  = inv(Twc_curr) @ P_world
  or, without going to world, P_curr = T_rel @ P_prev_cam  (the two agree).

  v1's C-group result (only 3.6% of pixels rejected) is therefore withdrawn and the
  C group is re-run with this module.
"""
import numpy as np


def backproject(depth_m, K):
    """depth (HxW metres, 0 = invalid) -> Nx3 points in that camera frame, plus mask."""
    H, W = depth_m.shape
    uu, vv = np.meshgrid(np.arange(W), np.arange(H))
    v = depth_m > 0
    z = depth_m[v]
    x = (uu[v] - K['cx']) * z / K['fx']
    y = (vv[v] - K['cy']) * z / K['fy']
    return np.stack([x, y, z], axis=1), v


def warp_depth(depth_prev, K, Twc_prev, Twc_curr, img_shape):
    """Predict the depth image of the CURRENT camera from the PREVIOUS one.

    Returns (zpred, hit). zpred is NaN where nothing was projected. When several
    points land on the same pixel the NEAREST one wins (z-buffer).
    """
    H, W = img_shape
    Pp, _ = backproject(depth_prev, K)
    if len(Pp) == 0:
        return np.full((H, W), np.nan), np.zeros((H, W), bool)
    # previous camera -> world -> current camera
    Pw = (Twc_prev[:3, :3] @ Pp.T).T + Twc_prev[:3, 3]
    Tcw_curr = np.linalg.inv(Twc_curr)
    Pn = (Tcw_curr[:3, :3] @ Pw.T).T + Tcw_curr[:3, 3]
    z = Pn[:, 2]
    ok = z > 1e-6
    if not ok.any():
        return np.full((H, W), np.nan), np.zeros((H, W), bool)
    u = K['fx'] * Pn[ok, 0] / z[ok] + K['cx']
    v = K['fy'] * Pn[ok, 1] / z[ok] + K['cy']
    zz = z[ok]
    inbox = (u >= 0) & (u < W - 0.5) & (v >= 0) & (v < H - 0.5)
    ui = np.rint(u[inbox]).astype(int)
    vi = np.rint(v[inbox]).astype(int)
    zi = zz[inbox]
    zpred = np.full((H, W), np.inf)
    # z-buffer: nearest surface wins. np.minimum.at handles duplicate (vi,ui) pairs.
    np.minimum.at(zpred, (vi, ui), zi)
    hit = np.isfinite(zpred)
    zpred[~hit] = np.nan
    return zpred, hit


def consistency_mask(depth_curr, zpred, hit, tau):
    """True where the observation AGREES with the prediction (keep).
    Pixels with no prediction are kept: absence of evidence is not evidence of motion.
    """
    keep = np.ones(depth_curr.shape, bool)
    valid_obs = depth_curr > 0
    comparable = hit & valid_obs
    bad = comparable & (np.abs(depth_curr - np.where(hit, zpred, 0.0)) > tau)
    keep[bad] = False
    return keep
