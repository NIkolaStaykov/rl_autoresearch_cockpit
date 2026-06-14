"""Evaluate a structured `hypothesis:` block against a queue's actual results.

Block shape (all optional except expect):

    hypothesis:
      axis: obs_noise.bias_scales.joint_pos   # the independent variable (a param)
      group: sensor_bundle                     # split runs into series by this param
      metric: success                          # 'success' | 'reward' | a summary key
      expect:
        baseline: decreasing                   # how metric should trend along axis
        proprio.target: flat

Per group we collect (axis_value, metric) from completed runs, sort by axis, and
classify the observed trend as increasing / flat / decreasing, then compare to the
expectation. Verdict per group: holds | partial | contradicted | insufficient.
Overall: holds (all hold) | contradicted (any contradicted) | partial | pending.
"""

from __future__ import annotations

from typing import Any, Optional

# Normalized-spread below this counts as "flat" rather than a real trend.
_FLAT_FRAC = 0.15

_OPPOSITE = {"increasing": "decreasing", "decreasing": "increasing"}


def _metric_value(run: dict, metric: str):
    """Eval value of the judged metric. `reward`/`success` are now {eval,train}
    dicts; the run's `success` already holds the queue's effective metric."""
    if metric in ("reward", "eval/episode_reward"):
        r = run.get("reward")
        return r.get("eval") if isinstance(r, dict) else r
    s = run.get("success")
    return s.get("eval") if isinstance(s, dict) else s


def _classify(points: list[tuple[float, float]]) -> str:
    """points sorted by axis ascending -> 'increasing'|'flat'|'decreasing'|'insufficient'."""
    ys = [y for _, y in points if y is not None]
    if len(ys) < 3:  # 2-point "trends" are too noisy to call
        return "insufficient"
    spread = max(ys) - min(ys)
    scale = max(abs(max(ys)), abs(min(ys)), 1e-9)
    if spread / scale < _FLAT_FRAC:
        return "flat"
    slope = ys[-1] - ys[0]
    if abs(slope) < _FLAT_FRAC * scale:
        return "flat"
    return "increasing" if slope > 0 else "decreasing"


def _verdict(expected: str, observed: str) -> str:
    if observed == "insufficient":
        return "insufficient"
    if observed == expected:
        return "holds"
    if _OPPOSITE.get(expected) == observed:
        return "contradicted"
    return "partial"  # one is flat, the other a trend


def evaluate(hyp: Optional[dict], runs: list[dict]) -> Optional[dict]:
    if not hyp or "expect" not in hyp:
        return None
    axis = hyp.get("axis")
    group = hyp.get("group")
    metric = hyp.get("metric", "reward")
    expect = hyp.get("expect", {})
    if not axis:
        return None

    groups: dict[Any, list[tuple[float, float]]] = {}
    for r in runs:
        if r.get("status") not in ("done",):
            continue
        params = r.get("params") or {}
        if axis not in params:
            continue
        gval = params.get(group) if group else "all"
        x = params.get(axis)
        y = _metric_value(r, metric)
        if x is None:
            continue
        groups.setdefault(gval, []).append((x, y))

    series = []
    verdicts = []
    for gval, pts in groups.items():
        pts.sort(key=lambda p: p[0])
        observed = _classify(pts)
        expected = expect.get(gval)
        v = _verdict(expected, observed) if expected else None
        if v and v != "insufficient":
            verdicts.append(v)
        series.append({
            "group": gval,
            "expected": expected,
            "observed": observed,
            "verdict": v,
            "points": [{"x": x, "y": y} for x, y in pts],
        })

    if not verdicts:
        overall = "pending"
    elif any(v == "contradicted" for v in verdicts):
        overall = "contradicted"
    elif all(v == "holds" for v in verdicts):
        overall = "holds"
    else:
        overall = "partial"

    return {
        "axis": axis,
        "group": group,
        "metric": metric,
        "overall": overall,
        "series": series,
    }
