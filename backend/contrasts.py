"""Typed contrasts & claims — the auditable building blocks of an ablation argument.

Evidence flows bottom-up:

    ScalarContrast / RobustnessContrast   ->   Claim   ->   Claim (general)

A *contrast* is the atomic unit: "arm A {outperforms|matches|underperforms} arm B
on task T, under eval condition E", graded over a *distribution of seeds* with an
effect size + bootstrap CI + a pre-registered decision rule. A *claim* aggregates
contrasts (or sub-claims) under an explicit rule, carries a scope boundary (what it
asserts vs what was actually tested) and a list of falsifiers.

This module is the wandb-wired grader: it reads the run dicts the cockpit already
assembles in `discovery.queue_detail` (params + reward/success + divergence flag),
so an "arm" is just a *param selector* over a queue's runs and its "seeds" are the
runs that match. The per-run `divergence.flag` (computed in `metrics.divergence`,
from early_stop's KL/collapse thresholds) is the diverged mask — given PPO's
intermittent ~1/4 seed divergence, that is load-bearing, not cosmetic.

Pure stdlib (no numpy): the cockpit stays jax/mujoco-free. Graders return plain
JSON-able dicts at the API boundary, matching the rest of the backend.

Authoring (read-through, nothing persisted by the cockpit):

  * same-queue contrasts — a `contrasts:` block in the queue YAML, graded against
    that queue's runs (mirrors the existing `hypothesis:` block). See `evaluate`.
  * cross-queue claims — `learning/claims/*.yaml`, each child contrast tagging the
    `queue:` it draws its arms from. See `claims.py`.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Optional, Sequence


# --------------------------------------------------------------------------- #
# Vocabulary
# --------------------------------------------------------------------------- #
class Relation(str, Enum):
    OUTPERFORMS = "outperforms"      # superiority   (one-sided)
    UNDERPERFORMS = "underperforms"  # inferiority   (one-sided)
    MATCHES = "matches"              # equivalence   (needs a margin; TOST-style)


class Population(str, Enum):
    ALL = "all"              # include diverged seeds (penalizes training reliability)
    CONVERGED = "converged"  # condition on training success; div-rate reported alongside


class Aggregation(str, Enum):
    ALL = "all"            # every child must hold
    MAJORITY = "majority"
    ANY = "any"            # sufficiency-by-existence


# Verdict vocabulary mirrors hypothesis.py: holds | refuted | insufficient (| pending).
HOLDS, REFUTED, INSUFFICIENT, PENDING = "holds", "refuted", "insufficient", "pending"


@dataclass(frozen=True)
class MetricRef:
    """Which logged quantity, in which namespace. e.g. success.eval, reward.train."""
    kind: str   # 'reward' | 'success'  (keys the cockpit puts on each run dict)
    split: str  # 'eval'   | 'train'

    @classmethod
    def parse(cls, s: str) -> "MetricRef":
        kind, _, split = s.partition(".")
        return cls(kind=kind or "success", split=split or "eval")

    def of(self, run: dict) -> Optional[float]:
        block = run.get(self.kind)
        if not isinstance(block, dict):
            return None
        v = block.get(self.split)
        return float(v) if isinstance(v, (int, float)) else None

    def __str__(self) -> str:
        return f"{self.kind}.{self.split}"


@dataclass(frozen=True)
class DecisionRule:
    """Pre-registered: fixed before results land. The grader refuses to act without it."""
    metric: MetricRef
    relation: Relation
    min_seeds: int = 3                 # below this -> 'insufficient', never a verdict
    margin: Optional[float] = None     # required for MATCHES: the equivalence half-width δ
    population: Population = Population.CONVERGED
    n_boot: int = 2000
    seed: int = 0                      # bootstrap RNG seed, for reproducible CIs

    def __post_init__(self):
        if self.relation is Relation.MATCHES and self.margin is None:
            raise ValueError("MATCHES is an equivalence claim and requires a margin δ.")


# --------------------------------------------------------------------------- #
# Seed samples (drawn from the cockpit's run dicts)
# --------------------------------------------------------------------------- #
@dataclass
class SeedSamples:
    values: list[float]      # one metric value per seed-run (on the chosen population)
    n_total: int             # runs matched before dropping diverged / missing
    n_diverged: int

    @property
    def div_rate(self) -> Optional[float]:
        return self.n_diverged / self.n_total if self.n_total else None

    @property
    def n(self) -> int:
        return len(self.values)


def _selector_matches(run: dict, selector: dict) -> bool:
    params = run.get("params") or {}
    return all(params.get(k) == v for k, v in selector.items())


def _is_diverged(run: dict) -> bool:
    div = run.get("divergence") or {}
    return div.get("flag") == "diverged"


def samples_for(runs: Sequence[dict], selector: dict, rule: DecisionRule) -> SeedSamples:
    """Collect a seed population: completed runs matching `selector`, metric present.

    CONVERGED drops diverged seeds; ALL keeps them. Divergence count is always
    tracked so a 'matches' verdict can't quietly mean 'trained more reliably'.
    """
    matched = [r for r in runs if r.get("status") == "done" and _selector_matches(r, selector)]
    n_total = len(matched)
    n_div = sum(1 for r in matched if _is_diverged(r))
    keep = matched if rule.population is Population.ALL else [r for r in matched if not _is_diverged(r)]
    vals = [v for v in (rule.metric.of(r) for r in keep) if v is not None]
    return SeedSamples(values=vals, n_total=n_total, n_diverged=n_div)


# --------------------------------------------------------------------------- #
# Statistics — rank-based + bootstrap, pure stdlib
# --------------------------------------------------------------------------- #
def _mean(xs: Sequence[float]) -> float:
    return sum(xs) / len(xs)


def _bootstrap_diff(a: Sequence[float], b: Sequence[float], n_boot: int, rng: random.Random):
    """Bootstrap CI on mean(a) - mean(b). Resamples each arm with replacement."""
    na, nb = len(a), len(b)
    eff = _mean(a) - _mean(b)
    diffs = []
    for _ in range(n_boot):
        sa = sum(a[rng.randrange(na)] for _ in range(na)) / na
        sb = sum(b[rng.randrange(nb)] for _ in range(nb)) / nb
        diffs.append(sa - sb)
    diffs.sort()
    lo = diffs[int(0.025 * n_boot)]
    hi = diffs[min(int(0.975 * n_boot), n_boot - 1)]
    return eff, lo, hi


def _prob_superiority(a: Sequence[float], b: Sequence[float]) -> float:
    """P(random a-seed > random b-seed). Robust to the bimodal seed outcomes that
    break the normality Cohen's d assumes; 0.5 == no difference."""
    wins = ties = 0
    for x in a:
        for y in b:
            if x > y:
                wins += 1
            elif x == y:
                ties += 1
    return (wins + 0.5 * ties) / (len(a) * len(b))


# --------------------------------------------------------------------------- #
# Scalar contrast
# --------------------------------------------------------------------------- #
@dataclass
class ScalarContrast:
    """'arm_a {relation} arm_b on `task`, under eval condition `eval_mod`.'

    arm_a / arm_b are param selectors over a queue's runs. eval_mod is descriptive
    (the test-time perturbation those selectors encode); single-delta is checked
    from the selectors themselves.
    """
    arm_a: dict
    arm_b: dict
    rule: DecisionRule
    task: str = ""
    eval_mod: str = ""

    def delta(self) -> list[str]:
        keys = set(self.arm_a) | set(self.arm_b)
        return [k for k in sorted(keys) if self.arm_a.get(k) != self.arm_b.get(k)]

    @property
    def confounded(self) -> bool:
        return len(self.delta()) != 1


def grade_scalar(c: ScalarContrast, runs: Sequence[dict]) -> dict:
    sa = samples_for(runs, c.arm_a, c.rule)
    sb = samples_for(runs, c.arm_b, c.rule)
    out: dict[str, Any] = {
        "kind": "scalar",
        "task": c.task,
        "eval_mod": c.eval_mod,
        "metric": str(c.rule.metric),
        "relation": c.rule.relation.value,
        "margin": c.rule.margin,
        "population": c.rule.population.value,
        "confounded": c.confounded,
        "delta": c.delta(),
        "arm_a": {"selector": c.arm_a, "n": sa.n, "div_rate": sa.div_rate, "mean": _mean(sa.values) if sa.n else None},
        "arm_b": {"selector": c.arm_b, "n": sb.n, "div_rate": sb.div_rate, "mean": _mean(sb.values) if sb.n else None},
    }
    if sa.n < c.rule.min_seeds or sb.n < c.rule.min_seeds:
        out["verdict"] = INSUFFICIENT
        out["note"] = f"need >= {c.rule.min_seeds} converged seeds/arm (have {sa.n}, {sb.n})"
        return out

    rng = random.Random(c.rule.seed)
    eff, lo, hi = _bootstrap_diff(sa.values, sb.values, c.rule.n_boot, rng)
    p_sup = _prob_superiority(sa.values, sb.values)
    out.update({"effect": eff, "ci": [lo, hi], "prob_superiority": p_sup})

    rel, m = c.rule.relation, c.rule.margin
    if rel is Relation.OUTPERFORMS:
        holds = lo > 0
    elif rel is Relation.UNDERPERFORMS:
        holds = hi < 0
    else:  # MATCHES — whole CI inside (-δ, +δ)
        holds = (lo > -m) and (hi < m)
    out["verdict"] = HOLDS if holds else REFUTED
    if c.confounded:
        out["note"] = "CONFOUNDED: arms differ in >1 dimension — not clean evidence"
    return out


# --------------------------------------------------------------------------- #
# Robustness contrast — a degradation *curve*, not a scalar
# --------------------------------------------------------------------------- #
@dataclass
class RobustnessContrast:
    """Compare how two arms degrade as a swept eval perturbation grows.

    base_a / base_b: the two policies' selectors *minus* the swept param.
    sweep_param + magnitudes: the perturbation axis. At each magnitude we add
    {sweep_param: mag} to each base selector and pull that arm's mean metric.
    """
    base_a: dict
    base_b: dict
    sweep_param: str
    magnitudes: Sequence[float]
    rule: DecisionRule
    threshold: float = 0.0   # perf below this = "broken"; breakdown point is first crossing
    task: str = ""

    def _curve(self, runs, base) -> list[Optional[float]]:
        curve = []
        for mag in self.magnitudes:
            s = samples_for(runs, {**base, self.sweep_param: mag}, self.rule)
            curve.append(_mean(s.values) if s.n >= self.rule.min_seeds else None)
        return curve


def _trapz(ys: Sequence[float], xs: Sequence[float]) -> float:
    return sum((ys[i] + ys[i + 1]) / 2 * (xs[i + 1] - xs[i]) for i in range(len(xs) - 1))


def _breakdown(curve, xs, threshold) -> Optional[float]:
    for x, y in zip(xs, curve):
        if y is not None and y < threshold:
            return x
    return None  # never broke within the swept range


def grade_robustness(c: RobustnessContrast, runs: Sequence[dict]) -> dict:
    xs = list(c.magnitudes)
    ca, cb = c._curve(runs, c.base_a), c._curve(runs, c.base_b)
    out: dict[str, Any] = {
        "kind": "robustness",
        "task": c.task,
        "metric": str(c.rule.metric),
        "sweep_param": c.sweep_param,
        "magnitudes": xs,
        "curve_a": ca,
        "curve_b": cb,
        "breakdown_a": _breakdown(ca, xs, c.threshold),
        "breakdown_b": _breakdown(cb, xs, c.threshold),
    }
    # AUC needs a fully-populated curve; otherwise the comparison is insufficient.
    if any(v is None for v in ca) or any(v is None for v in cb):
        out["verdict"] = INSUFFICIENT
        out["note"] = "incomplete degradation curve (a magnitude lacks enough seeds)"
        return out
    auc_a, auc_b = _trapz(ca, xs), _trapz(cb, xs)
    out.update({"auc_a": auc_a, "auc_b": auc_b})
    # 'more robust' = larger area under the (higher-is-better) degradation curve.
    if c.rule.relation is Relation.OUTPERFORMS:
        out["verdict"] = HOLDS if auc_a > auc_b else REFUTED
    elif c.rule.relation is Relation.UNDERPERFORMS:
        out["verdict"] = HOLDS if auc_a < auc_b else REFUTED
    else:
        out["verdict"] = HOLDS if abs(auc_a - auc_b) <= (c.rule.margin or 0) else REFUTED
    return out


# --------------------------------------------------------------------------- #
# Claims — aggregate child verdicts under an explicit rule + scope + falsifiers
# --------------------------------------------------------------------------- #
@dataclass
class Scope:
    covers: list[str] = field(default_factory=list)   # condition space the claim asserts over
    tested: list[str] = field(default_factory=list)   # what was actually measured

    @property
    def gap(self) -> list[str]:                        # asserted-but-untested = inductive risk
        return [c for c in self.covers if c not in self.tested]


def grade_claim(statement: str, child_verdicts: Sequence[dict],
                aggregation: Aggregation, scope: Optional[Scope] = None,
                falsifiers: Optional[list[str]] = None) -> dict:
    """Combine already-graded children (contrasts or sub-claims) into a claim verdict."""
    scope = scope or Scope()
    decided = [v for v in child_verdicts if v.get("verdict") in (HOLDS, REFUTED)]
    n_hold = sum(1 for v in decided if v["verdict"] == HOLDS)
    if not decided:
        overall = PENDING
    elif aggregation is Aggregation.ALL:
        overall = HOLDS if n_hold == len(decided) else REFUTED
    elif aggregation is Aggregation.ANY:
        overall = HOLDS if n_hold > 0 else REFUTED
    else:  # MAJORITY
        overall = HOLDS if n_hold > len(decided) / 2 else REFUTED
    return {
        "statement": statement,
        "aggregation": aggregation.value,
        "overall": overall,
        "n_holds": n_hold,
        "n_decided": len(decided),
        "n_children": len(child_verdicts),
        "scope_gap": scope.gap,        # always surfaced: what the claim does NOT test
        "falsifiers": list(falsifiers or []),
        "children": list(child_verdicts),
    }


# --------------------------------------------------------------------------- #
# YAML block parsing
# --------------------------------------------------------------------------- #
def _rule_from(d: dict) -> DecisionRule:
    return DecisionRule(
        metric=MetricRef.parse(str(d.get("metric", "success.eval"))),
        relation=Relation(d.get("relation", "outperforms")),
        min_seeds=int(d.get("min_seeds", 3)),
        margin=d.get("margin"),
        population=Population(d.get("population", "converged")),
        n_boot=int(d.get("n_boot", 2000)),
        seed=int(d.get("seed", 0)),
    )


def contrast_from(d: dict) -> ScalarContrast | RobustnessContrast:
    rule = _rule_from(d)
    if "sweep_param" in d:
        return RobustnessContrast(
            base_a=d["arm_a"], base_b=d["arm_b"], sweep_param=d["sweep_param"],
            magnitudes=d["magnitudes"], rule=rule,
            threshold=float(d.get("threshold", 0.0)), task=d.get("task", ""))
    return ScalarContrast(
        arm_a=d["arm_a"], arm_b=d["arm_b"], rule=rule,
        task=d.get("task", ""), eval_mod=d.get("eval_mod", ""))


def grade_one(d: dict, runs: Sequence[dict]) -> dict:
    c = contrast_from(d)
    return grade_robustness(c, runs) if isinstance(c, RobustnessContrast) else grade_scalar(c, runs)


def evaluate(block: Optional[list], runs: Sequence[dict]) -> Optional[dict]:
    """Grade a queue YAML's `contrasts:` block against that queue's runs.

    Mirrors hypothesis.evaluate's call shape so discovery.queue_detail can drop it
    in. Returns None when there is no block.
    """
    if not block:
        return None
    graded = [grade_one(d, runs) for d in block]
    verdicts = [g["verdict"] for g in graded if g["verdict"] in (HOLDS, REFUTED)]
    if not verdicts:
        overall = PENDING
    elif all(v == HOLDS for v in verdicts):
        overall = HOLDS
    elif any(v == REFUTED for v in verdicts):
        overall = REFUTED
    else:
        overall = PENDING
    return {"overall": overall, "contrasts": graded}


# --------------------------------------------------------------------------- #
# Self-check (no real data, no deps): `python -m backend.contrasts`
# --------------------------------------------------------------------------- #
def _selfcheck() -> None:
    def run(bundle, val, diverged=False):
        return {"status": "done", "params": {"sensor_bundle": bundle},
                "success": {"eval": val}, "divergence": {"flag": "diverged" if diverged else "ok"}}

    # proprio clearly beats a degraded bundle, with one diverged proprio seed dropped.
    runs = (
        [run("proprio", v) for v in (0.81, 0.84, 0.79, 0.83)]
        + [run("proprio", 0.05, diverged=True)]            # dropped under CONVERGED
        + [run("noisy", v) for v in (0.40, 0.38, 0.45, 0.41)]
    )
    sup = grade_scalar(ScalarContrast(
        arm_a={"sensor_bundle": "proprio"}, arm_b={"sensor_bundle": "noisy"},
        rule=DecisionRule(MetricRef.parse("success.eval"), Relation.OUTPERFORMS, min_seeds=3),
        task="pinch", eval_mod="noisy obs"), runs)
    assert sup["verdict"] == HOLDS, sup
    assert sup["arm_a"]["n"] == 4 and abs(sup["arm_a"]["div_rate"] - 0.2) < 1e-9, sup
    assert sup["prob_superiority"] == 1.0, sup

    # equivalence requires a margin and a CI that fits inside it.
    eq_runs = [run("a", v) for v in (0.80, 0.82, 0.81)] + [run("b", v) for v in (0.79, 0.81, 0.80)]
    eq = grade_scalar(ScalarContrast(
        arm_a={"sensor_bundle": "a"}, arm_b={"sensor_bundle": "b"},
        rule=DecisionRule(MetricRef.parse("success.eval"), Relation.MATCHES, min_seeds=3, margin=0.05)), eq_runs)
    assert eq["verdict"] == HOLDS, eq

    try:
        DecisionRule(MetricRef.parse("success.eval"), Relation.MATCHES)
    except ValueError:
        pass
    else:
        raise AssertionError("MATCHES without margin should raise")

    # confounded: arms differ in 2 dims.
    cf = ScalarContrast(arm_a={"x": 1, "y": 1}, arm_b={"x": 2, "y": 2},
                        rule=DecisionRule(MetricRef.parse("success.eval"), Relation.OUTPERFORMS))
    assert cf.confounded and cf.delta() == ["x", "y"], cf.delta()

    claim = grade_claim("proprio sufficient under {noisy,nominal}", [sup, eq],
                        Aggregation.ALL, Scope(covers=["noisy", "nominal", "low_friction"],
                                               tested=["noisy", "nominal"]),
                        falsifiers=["proprio underperforms under unseen friction"])
    assert claim["overall"] == HOLDS and claim["scope_gap"] == ["low_friction"], claim
    print("contrasts self-check OK")


if __name__ == "__main__":
    _selfcheck()
