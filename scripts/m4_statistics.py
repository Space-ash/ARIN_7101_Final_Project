"""Exploratory A1-A6 analyses on already aggregated, paired dialogue results.

This module neither generates dialogues nor changes the E1 primary analysis.
Every optional inferential model is recorded in its output. In particular, A5
requires explicit priors; these are evaluation priors, not the CTS prior.
"""
from itertools import combinations
import hashlib
import math
import warnings

import numpy as np
import pandas as pd
from scipy import integrate, optimize, special, stats

from m4_analysis import ARMS, METHODS, METRICS, SCENARIOS, _check_frame, _check_values


ANALYSES = ("A1", "A2", "A3", "A4", "A5", "A6")
DEFAULT_ANALYSES = ("A1", "A2", "A3", "A4", "A6")
ROPE_KEYS = {"mu_prior_sd", "sigma_prior_shape", "sigma_prior_scale", "delta"}


def _number(value, name, lower=0, strict=True):
    if (isinstance(value, (bool, np.bool_)) or not isinstance(value, (int, float))
            or not np.isfinite(value) or (value <= lower if strict else value < lower)):
        raise ValueError("Invalid " + name)
    return float(value)


def _positive_int(value, name):
    if type(value) is not int or value < 1:
        raise ValueError("Invalid positive integer: " + name)
    return value


def _options(options, cfg):
    options = {} if options is None else dict(options)
    allowed = {"analyses", "metrics", "bootstrap_resamples", "bootstrap_methods",
               "confidence", "tie_tolerance", "sign_flip_resamples",
               "sign_flip_exact_max_n", "seed", "rope"}
    if set(options) - allowed:
        raise ValueError("Unknown statistical options: " + str(sorted(set(options) - allowed)))
    result = dict(analyses=list(DEFAULT_ANALYSES), metrics=["utility"],
                  bootstrap_resamples=[cfg.get("n_bootstrap", 2000), 10000],
                  bootstrap_methods=["percentile", "BCa"], confidence=0.95,
                  tie_tolerance=1e-12, sign_flip_resamples=10000,
                  sign_flip_exact_max_n=16, seed=cfg.get("bootstrap_seed", 2026))
    result.update(options)
    for key, allowed_values in [("analyses", ANALYSES), ("metrics", METRICS),
                                ("bootstrap_methods", ("percentile", "BCa"))]:
        values = result[key]
        if (not isinstance(values, (tuple, list)) or not values
                or any(v not in allowed_values for v in values)
                or len(set(values)) != len(values)):
            raise ValueError("Invalid " + key)
    counts = result["bootstrap_resamples"]
    if not isinstance(counts, (tuple, list)) or not counts:
        raise ValueError("bootstrap_resamples must be a nonempty list")
    result["bootstrap_resamples"] = list(dict.fromkeys(
        _positive_int(v, "bootstrap_resamples") for v in counts))
    result["confidence"] = _number(result["confidence"], "confidence")
    if result["confidence"] >= 1:
        raise ValueError("confidence must be below one")
    result["tie_tolerance"] = _number(result["tie_tolerance"], "tie_tolerance", strict=False)
    _positive_int(result["sign_flip_resamples"], "sign_flip_resamples")
    if (type(result["sign_flip_exact_max_n"]) is not int
            or not 0 <= result["sign_flip_exact_max_n"] <= 20):
        raise ValueError("sign_flip_exact_max_n must be an integer from 0 to 20")
    if type(result["seed"]) is not int or result["seed"] < 0:
        raise ValueError("seed must be a nonnegative integer")
    if "A5" in result["analyses"]:
        if "rope" not in result or not isinstance(result["rope"], dict):
            raise ValueError("A5 requires an explicit rope prior and delta")
        if set(result["rope"]) != ROPE_KEYS:
            raise ValueError("rope must specify exactly " + str(sorted(ROPE_KEYS)))
        result["rope"] = {key: _number(value, "rope." + key)
                          for key, value in result["rope"].items()}
    return result


def _derived_seed(seed, *labels):
    text = ":".join(map(str, (seed, *labels))).encode("utf-8")
    return int.from_bytes(hashlib.sha256(text).digest()[:8], "little")


def _validate_metrics(metrics, baselines, cfg):
    if "alg_seed" in metrics or "t" in metrics:
        raise ValueError("Aggregate questions and algorithm seeds within dialogue first")
    _check_frame(metrics, ["scenario", "seed", "method"])
    _check_values(metrics, cfg, binary=False)
    if set(metrics.scenario) != set(SCENARIOS) or set(baselines) != set(SCENARIOS):
        raise ValueError("Both scenarios and their development baselines are required")
    if any(value not in ARMS for value in baselines.values()):
        raise ValueError("Development baseline must be a fixed arm")
    if not metrics.seed.map(lambda s: isinstance(s, (int, np.integer))
                            and not isinstance(s, (bool, np.bool_)) and s >= 0).all():
        raise ValueError("Dialogue seeds must be nonnegative integers")
    seed_sets = []
    for scenario in SCENARIOS:
        part = metrics[metrics.scenario == scenario]
        seeds = sorted(part.seed.unique())
        if len(seeds) < 2:
            raise ValueError("At least two independent dialogues per scenario are required")
        expected = {(seed, method) for seed in seeds for method in METHODS}
        if set(part[["seed", "method"]].itertuples(index=False, name=None)) != expected:
            raise ValueError("Incomplete or unexpected paired dialogue methods")
        seed_sets.append(set(seeds))
    if seed_sets[0] & seed_sets[1]:
        raise ValueError("Different scenarios must not reuse dialogue seed IDs")


def _differences(values):
    values = np.asarray(values, dtype=float)
    if values.ndim != 1 or len(values) < 2 or not np.isfinite(values).all():
        raise ValueError("Expected at least two finite dialogue differences")
    return values


def bootstrap_interval(values, resamples=2000, method="percentile", confidence=0.95, seed=2026):
    """Bootstrap the mean of paired differences, not two independent samples."""
    values = _differences(values)
    _positive_int(resamples, "resamples")
    if method not in ("percentile", "BCa") or not 0 < confidence < 1:
        raise ValueError("Invalid bootstrap method/confidence")
    result = dict(bootstrap_method=method, resamples=resamples, confidence=confidence,
                  seed=int(seed), low=np.nan, high=np.nan, status="ok", warning="")
    if np.ptp(values) == 0:
        if method == "BCa":
            result.update(status="undefined_degenerate_bca",
                          warning="BCa acceleration is undefined for a constant sample")
        else:
            result.update(low=float(values[0]), high=float(values[0]),
                          status="degenerate_constant_sample")
        return result
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        # random_state is supported across the repository's scipy>=1.10 range.
        ci = stats.bootstrap((values,), np.mean, vectorized=True, paired=True,
                             n_resamples=resamples, batch=min(resamples, 2048),
                             confidence_level=confidence, method=method,
                             random_state=np.random.default_rng(seed)).confidence_interval
    result["warning"] = "; ".join(dict.fromkeys(str(w.message) for w in caught))
    if not np.isfinite([ci.low, ci.high]).all():
        result["status"] = "undefined_numerical_interval"
    else:
        result.update(low=float(ci.low), high=float(ci.high))
    return result


def paired_t(values, confidence=0.95):
    values = _differences(values)
    mean, sd = float(values.mean()), float(values.std(ddof=1))
    if np.ptp(values) == 0:
        return dict(statistic=np.nan, p_value=np.nan, low=mean, high=mean,
                    standard_error=0.0, confidence=confidence,
                    status="degenerate_zero" if mean == 0 else "degenerate_nonzero",
                    warning="Zero observed variance; t reference statistic is undefined")
    se = sd / math.sqrt(len(values))
    statistic = mean / se
    radius = float(stats.t.ppf((1 + confidence) / 2, len(values) - 1)) * se
    return dict(statistic=statistic, p_value=float(2 * stats.t.sf(abs(statistic), len(values) - 1)),
                standard_error=se, low=mean - radius, high=mean + radius,
                confidence=confidence, status="ok", warning="")


def sign_test(values, tie_tolerance=1e-12):
    values = _differences(values)
    wins, losses = int((values > tie_tolerance).sum()), int((values < -tie_tolerance).sum())
    count = wins + losses
    return dict(wins=wins, losses=losses, ties=len(values) - count,
                non_ties=count, conditional_win_rate=wins / count if count else np.nan,
                p_value=float(stats.binomtest(wins, count, 0.5).pvalue) if count else np.nan,
                tie_tolerance=tie_tolerance,
                status="ok" if count else "no_non_tied_dialogues")


def sign_flip(values, resamples=10000, seed=2026, tie_tolerance=1e-12, exact_max_n=16):
    """Two-sided |mean| test; needs sign symmetry or paired exchangeability."""
    values = _differences(values)
    _positive_int(resamples, "sign_flip_resamples")
    cleaned = values.copy()
    cleaned[np.abs(cleaned) <= tie_tolerance] = 0
    nonzero = cleaned[cleaned != 0]
    observed = abs(float(cleaned.mean()))
    threshold = observed - 16 * np.finfo(float).eps * max(1, observed)
    exact = len(nonzero) <= exact_max_n
    count = (1 << len(nonzero)) if exact else resamples
    extreme = 0
    rng = np.random.default_rng(seed)
    for start in range(0, count, 2048):
        size = min(2048, count - start)
        if exact:
            indices = np.arange(start, start + size, dtype=np.uint64)[:, None]
            signs = 2 * ((indices >> np.arange(len(nonzero), dtype=np.uint64)) & 1).astype(float) - 1
        else:
            signs = 2 * rng.integers(0, 2, size=(size, len(nonzero))) - 1
        draws = (signs @ nonzero) / len(values)
        extreme += int((np.abs(draws) >= threshold).sum())
    p = extreme / count if exact else (extreme + 1) / (count + 1)
    return dict(statistic=float(cleaned.mean()), p_value=float(p),
                calculation="exact_enumeration" if exact else "monte_carlo_plus_one",
                resamples=count, seed=int(seed), tie_tolerance=tie_tolerance, status="ok",
                assumption="Independent differences symmetric about zero or paired labels exchangeable")


def wilcoxon_test(values, tie_tolerance=1e-12):
    values = _differences(values)
    cleaned = values.copy()
    cleaned[np.abs(cleaned) <= tie_tolerance] = 0
    if tie_tolerance:
        # Quantize only for stable rank ties; this tolerance is not the ROPE.
        with np.errstate(over="ignore", invalid="ignore"):
            rounded = np.rint(cleaned / tie_tolerance) * tie_tolerance
        if np.isfinite(rounded).all():
            cleaned = rounded
    nonzero = cleaned[cleaned != 0]
    if not len(nonzero):
        return dict(statistic=0.0, p_value=1.0, calculation="all_zero", nonzero_n=0,
                    tie_tolerance=tie_tolerance, status="degenerate_zero", warning="")
    no_ties = len(np.unique(np.abs(nonzero))) == len(nonzero)
    method = "exact" if len(nonzero) == len(cleaned) and no_ties and len(cleaned) <= 50 else "approx"
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        result = stats.wilcoxon(cleaned, zero_method="wilcox", correction=False,
                               alternative="two-sided", method=method)
    if not np.isfinite([result.statistic, result.pvalue]).all():
        raise ValueError("Wilcoxon returned a nonfinite result")
    return dict(statistic=float(result.statistic), p_value=float(result.pvalue),
                calculation=method, nonzero_n=len(nonzero), tie_tolerance=tie_tolerance,
                status="ok", warning="; ".join(dict.fromkeys(str(w.message) for w in caught)))


def holm_adjust(p_values):
    """Adjusted p-values for the entire supplied, predeclared family."""
    values = np.asarray(p_values, dtype=float)
    if values.ndim != 1 or not len(values) or not np.isfinite(values).all() or ((values < 0) | (values > 1)).any():
        raise ValueError("Holm needs a nonempty vector of finite p-values in [0,1]")
    order = np.argsort(values, kind="stable")
    corrected = np.minimum(1, np.maximum.accumulate(values[order] * np.arange(len(values), 0, -1)))
    result = np.empty_like(values)
    result[order] = corrected
    return result


def rope_probabilities(values, *, mu_prior_sd, sigma_prior_shape, sigma_prior_scale, delta):
    """Independent Normal mean prior and inverse-Gamma variance prior.

    D_i|mu,v ~ Normal(mu,v); mu ~ Normal(0,mu_prior_sd**2);
    v=sigma**2 ~ InvGamma(shape,scale). The mean is integrated analytically;
    one-dimensional quadrature over log(v) averages its conditional Normal CDF.
    No learned bandit posterior or unreported default prior is used.
    """
    values = _differences(values)
    sd = _number(mu_prior_sd, "mu_prior_sd")
    a = _number(sigma_prior_shape, "sigma_prior_shape")
    b = _number(sigma_prior_scale, "sigma_prior_scale")
    delta = _number(delta, "delta")
    n, mean = len(values), float(values.mean())
    s2 = sd * sd
    if not np.isfinite(s2) or s2 == 0:
        raise ValueError("Invalid squared mean-prior scale")
    ss = float(np.dot(values - mean, values - mean))
    if not np.isfinite(ss) or not np.isfinite(mean * mean):
        raise ValueError("ROPE moments overflowed")
    log_ns2 = math.log(n * s2)

    def log_weight(z):
        if z < -700 or z > 700:
            return -np.inf
        log_denom = float(np.logaddexp(z, log_ns2))
        return (-(a + (n - 1) / 2) * z - log_denom / 2
                - (b + ss / 2) * math.exp(-z)
                - n * mean * mean * math.exp(-log_denom) / 2)

    # Include both plausible variance scales. Independent mean/variance priors
    # need not make the marginal variance posterior unimodal.
    scales = [s2, b / (a + 1), b + ss / max(1, n - 1), mean * mean + s2]
    lower = max(-690.0, min(math.log(v) for v in scales if v > 0) - 40)
    upper = min(690.0, max(math.log(v) for v in scales if v > 0) + 40)
    grid = np.linspace(lower, upper, 1025)
    logs = np.array([log_weight(z) for z in grid])
    peaks = [i for i in range(1, len(grid) - 1) if logs[i] >= logs[i - 1] and logs[i] >= logs[i + 1]]
    if not peaks:
        raise ValueError("ROPE quadrature could not bracket posterior mass")
    modes = []
    for i in peaks:
        result = optimize.minimize_scalar(lambda z: -log_weight(z),
                                         bounds=(grid[i - 1], grid[i + 1]), method="bounded")
        if not result.success:
            raise ValueError("ROPE mode search failed")
        modes.append(float(result.x))
    shift = max(log_weight(z) for z in modes)
    if not np.isfinite(shift) or max(log_weight(lower), log_weight(upper)) - shift > -35:
        raise ValueError("ROPE posterior tails are not resolved within integration range")

    def integrand(z, component):
        w = math.exp(log_weight(z) - shift)
        if not w or component is None:
            return w
        # Conditional Normal posterior for mu at fixed variance v.
        ratio = float(special.expit(log_ns2 - z))
        location = mean * ratio
        variance = s2 * float(special.expit(z - log_ns2))
        if variance <= 0:
            raise ValueError("ROPE conditional posterior variance underflow")
        posterior_sd = math.sqrt(variance)
        low = (-delta - location) / posterior_sd
        high = (delta - location) / posterior_sd
        if component == "loss":
            probability = special.ndtr(low)
        elif component == "gain":
            probability = special.ndtr(-high)
        else:
            # Difference of survival functions avoids catastrophic cancellation
            # when both interval endpoints are far in the positive tail.
            probability = (special.ndtr(-low) - special.ndtr(-high)
                           if low > 0 else special.ndtr(high) - special.ndtr(low))
        return w * float(probability)

    totals, errors = {}, {}
    for component in [None, "loss", "equivalent", "gain"]:
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always", integrate.IntegrationWarning)
            value, error = integrate.quad(lambda z: integrand(z, component), lower, upper,
                                          points=modes, epsabs=1e-10, epsrel=1e-9, limit=300)
        if caught or not np.isfinite([value, error]).all():
            raise ValueError("ROPE quadrature failed: " + "; ".join(str(w.message) for w in caught))
        totals[component], errors[component] = value, error
    norm = totals[None]
    if norm <= 0 or errors[None] / norm > 1e-6:
        raise ValueError("ROPE normalization is not numerically resolved")
    probabilities = np.array([totals[k] / norm for k in ["loss", "equivalent", "gain"]])
    if (np.any(probabilities < -1e-10) or np.any(probabilities > 1 + 1e-10)
            or abs(probabilities.sum() - 1) > 1e-7):
        raise ValueError("ROPE posterior probabilities did not normalize")
    return dict(p_loss=float(probabilities[0]), p_equivalent=float(probabilities[1]),
                p_gain=float(probabilities[2]), delta=delta,
                mu_prior_sd=sd, sigma_prior_shape=a, sigma_prior_scale=b,
                variance_prior="InverseGamma(shape,scale) on sigma_squared",
                mean_prior="Normal(0,mu_prior_sd_squared), independent of variance",
                likelihood="iid Normal dialogue utility differences",
                integration_relative_error=max(errors.values()) / norm,
                log_variance_lower=lower, log_variance_upper=upper, status="ok")


def statistical_analysis(metrics, baselines, cfg, options=None):
    """Return named exploratory tables; see _options for supported settings.

    A5 is deliberately excluded from defaults. Supply analyses including A5
    and the complete rope object to run a chosen, explicit evaluation model.
    Statistical input/model errors raise, so a runner can retain a failed run.
    Undefined degenerate intervals are rows with status and missing endpoints.
    """
    settings = _options(options, cfg)
    _validate_metrics(metrics, baselines, cfg)
    output = {}

    def emit(table, row):
        output.setdefault(table, []).append(row)

    for scenario in SCENARIOS:
        part = metrics[metrics.scenario == scenario]
        seeds = sorted(part.seed.unique())
        paired = {method: part[part.method == method].set_index("seed").loc[seeds]
                  for method in METHODS}
        comparisons = [("cts_vs_fixed", "LaplaceCTS", baselines[scenario]),
                       ("cts_vs_ts", "LaplaceCTS", "TS"),
                       ("cts_vs_router", "LaplaceCTS", "RuleRouter"),
                       ("ts_vs_fixed", "TS", baselines[scenario])]
        for metric in settings["metrics"]:
            for name, method, reference in comparisons:
                values = (paired[method][metric] - paired[reference][metric]).to_numpy(dtype=float)
                common = dict(scenario=scenario, comparison=name, method=method, reference=reference,
                              metric=metric, n=len(values), effect=float(values.mean()),
                              independent_unit="dialogue", analysis_role="exploratory",
                              family_adjusted=False)
                seed = _derived_seed(settings["seed"], scenario, metric, name)
                if "A1" in settings["analyses"]:
                    for count in settings["bootstrap_resamples"]:
                        for bootstrap_method in settings["bootstrap_methods"]:
                            row = bootstrap_interval(values, count, bootstrap_method, settings["confidence"], seed)
                            emit("statistical_bootstrap", dict(common, **row))
                if "A2" in settings["analyses"]:
                    emit("statistical_t", dict(common, **paired_t(values, settings["confidence"]),
                         assumption="Independent differences; exact small-sample t reference requires Normal differences"))
                if "A3" in settings["analyses"]:
                    emit("statistical_sign", dict(common, **sign_test(values, settings["tie_tolerance"]),
                         hypothesis="P(win | non-tie)=0.5 for independent dialogues"))
                if "A4" in settings["analyses"]:
                    emit("statistical_sign_flip", dict(common, **sign_flip(
                        values, settings["sign_flip_resamples"], seed, settings["tie_tolerance"],
                        settings["sign_flip_exact_max_n"])))
                    emit("statistical_wilcoxon", dict(common, **wilcoxon_test(values, settings["tie_tolerance"]),
                         assumption="Independent differences with a symmetric distribution about a common location"))
                if "A5" in settings["analyses"]:
                    if metric != "utility":
                        raise ValueError("A5 ROPE delta and priors are defined for utility only")
                    emit("statistical_rope", dict(common, **rope_probabilities(values, **settings["rope"])))
            if "A6" in settings["analyses"]:
                matrix = np.column_stack([paired[m][metric].to_numpy() for m in METHODS])
                # Rank 1 is best, accounting for the lower-is-better metrics.
                direction = 1 if metric in ("cost", "outdated") else -1
                ranks = stats.rankdata(direction * matrix, method="average", axis=1)
                all_tied = np.all(np.ptp(matrix, axis=1) == 0)
                if all_tied:
                    statistic, p_value, status = 0.0, 1.0, "all_within_dialogue_ties"
                else:
                    result = stats.friedmanchisquare(*matrix.T)
                    statistic, p_value, status = float(result.statistic), float(result.pvalue), "ok"
                    if not np.isfinite([statistic, p_value]).all():
                        raise ValueError("Friedman returned a nonfinite result")
                emit("friedman", dict(scenario=scenario, metric=metric, n=len(seeds), methods=len(METHODS),
                     statistic=statistic, p_value=p_value, status=status, analysis_role="exploratory",
                     reference_distribution="asymptotic chi-square; small-dialogue accuracy not guaranteed"))
                for index, method in enumerate(METHODS):
                    emit("method_ranks", dict(scenario=scenario, metric=metric, method=method,
                         n=len(seeds), mean_rank=float(ranks[:, index].mean()), rank_one="best",
                         analysis_role="exploratory"))
                posthoc = []
                for left, right in combinations(METHODS, 2):
                    values = (paired[left][metric] - paired[right][metric]).to_numpy(dtype=float)
                    row = dict(scenario=scenario, metric=metric, method=left, reference=right,
                               n=len(values), effect=float(values.mean()),
                               analysis_role="exploratory", test="paired_wilcoxon",
                               assumption="Independent symmetric paired differences",
                               **wilcoxon_test(values, settings["tie_tolerance"]))
                    posthoc.append(row)
                adjusted = holm_adjust([row["p_value"] for row in posthoc])
                for row, value in zip(posthoc, adjusted):
                    row.update(holm_p_value=float(value), family_size=len(posthoc),
                               family="all 21 method pairs within this scenario and metric",
                               family_adjusted=True, alpha=1-settings["confidence"],
                               reject=bool(value <= 1-settings["confidence"]))
                    emit("posthoc_holm", row)
    return {name: pd.DataFrame(rows) for name, rows in output.items()}
