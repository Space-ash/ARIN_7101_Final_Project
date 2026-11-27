"""Isolated experimental adapters for E2/E4/E5/E6/E7.

The release notebook remains the implementation source. Each namespace is loaded
fresh; no notebook, shared function global, approval, or formal registry is edited.
Only resolved_tfidf is changed by retrieval switches. The reader and RuleRouter
continue to receive the original question and original history messages.
"""
import ast
from copy import deepcopy
import json
import math
from pathlib import Path
import re
from time import perf_counter
from types import FunctionType

import numpy as np
import pandas as pd

from m4_analysis import ARMS, METHODS, validate_outcomes, validate_replay


DEFAULT_ADAPTER = {
    "feature_mode": "full",
    "resolved_top_k": 8,
    "resolve_pronouns": True,
    "normalize_aliases": True,
    "preserve_focus": True,
}


def validate_config(cfg):
    """Validate experimental settings, including small non-formal fixtures."""
    for name in ("T", "refit_every"):
        if type(cfg.get(name)) is not int or cfg[name] < 1:
            raise ValueError(f"{name} must be a positive integer")
    for name, lower, strict in (("lambda", 0, False), ("cost_reference", 0, True),
                                ("prior_precision", 0, True)):
        value = cfg.get(name)
        if (type(value) not in (int, float) or not math.isfinite(value)
                or (value <= lower if strict else value < lower)):
            raise ValueError(f"Invalid {name}")
    budgets = cfg.get("budgets")
    if (not isinstance(budgets, dict) or set(budgets) != set(ARMS)
            or any(type(v) is not int or v < 0 for v in budgets.values())):
        raise ValueError("Expected four nonnegative integer body budgets")
    seeds = cfg.get("algorithm_seeds")
    if (not isinstance(seeds, list) or not seeds
            or any(type(v) is not int or v < 0 for v in seeds)
            or len(seeds) != len(set(seeds))):
        raise ValueError("algorithm_seeds must be distinct nonnegative integers")
    if "n_projects" in cfg and (type(cfg["n_projects"]) is not int or cfg["n_projects"] < 2):
        raise ValueError("n_projects must be at least two")
    for name in ("p_recent_stable", "p_recent_abrupt_before", "p_recent_abrupt_after",
                 "update_probability", "initial_conflict_fraction", "alias_probability"):
        if name in cfg:
            value = cfg[name]
            if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 1:
                raise ValueError(f"Invalid probability: {name}")
    if "n_bootstrap" in cfg and (type(cfg["n_bootstrap"]) is not int or cfg["n_bootstrap"] < 1):
        raise ValueError("n_bootstrap must be a positive integer")
    if "bootstrap_seed" in cfg and (type(cfg["bootstrap_seed"]) is not int or cfg["bootstrap_seed"] < 0):
        raise ValueError("bootstrap_seed must be a nonnegative integer")


def _adapter_options(variant):
    if not isinstance(variant, dict) or set(variant) - set(DEFAULT_ADAPTER):
        raise ValueError("Unknown experimental adapter option")
    options = dict(DEFAULT_ADAPTER, **variant)
    if options["feature_mode"] not in ("full", "constant"):
        raise ValueError("feature_mode must be full or constant")
    if type(options["resolved_top_k"]) is not int or options["resolved_top_k"] < 1:
        raise ValueError("resolved_top_k must be a positive integer")
    for key in ("resolve_pronouns", "normalize_aliases", "preserve_focus"):
        if type(options[key]) is not bool:
            raise ValueError(f"{key} must be boolean")
    return options


def load_namespace(notebook):
    """Load declarations into one fresh globals dict; never run export/demo cells."""
    notebook = Path(notebook).resolve()
    cells = json.loads(notebook.read_text(encoding="utf-8"))["cells"]
    ns = {"np": np, "pd": pd, "__name__": "m4_experimental_notebook"}
    protocol = [c for c in cells if c.get("id") == "shared-protocol-draft"]
    if len(protocol) != 1:
        raise ValueError("Expected exactly one shared protocol cell")
    exec(compile("".join(protocol[0]["source"]), "shared-protocol-draft", "exec"), ns)
    selected = []
    for cell in cells:
        identifier = cell.get("id", "")
        if cell.get("cell_type") != "code":
            continue
        if not (identifier.startswith(("m1-", "m2-", "m3-")) or identifier in (
                "m4-experiment-skeleton", "m4-checks-and-execution-workspace")):
            continue
        tree = ast.parse("".join(cell["source"]))
        tree.body = [node for node in tree.body if isinstance(node, (
            ast.Import, ast.ImportFrom, ast.FunctionDef, ast.AsyncFunctionDef,
            ast.ClassDef, ast.Assign, ast.AnnAssign))]
        exec(compile(tree, identifier, "exec"), ns)
        selected.append(identifier)
    required = ("generate_episode", "audit_truth", "evaluate_episode", "Selector",
                "replay_episode", "choose_fixed_baselines")
    if any(name not in ns for name in required):
        raise ValueError("Notebook is missing required experimental interfaces")
    ns["_variant_notebook"] = notebook
    ns["_variant_loaded_cells"] = selected
    ns["_variant_original_selector"] = ns["Selector"]
    ns["_variant_original_select_context"] = ns["select_context"]
    ns["_variant_original_rank_tfidf"] = ns["m2_rank_tfidf"]
    _install_adapter(ns, dict(DEFAULT_ADAPTER))
    return ns


def configure_namespace(ns, variant):
    """Return another fresh namespace configured with exactly this adapter.

    Configuration does not stack onto or mutate the supplied namespace. Ordinary
    algorithm/environment parameters remain in the cfg passed to run functions.
    """
    options = _adapter_options(variant)
    result = load_namespace(ns["_variant_notebook"])
    _install_adapter(result, options)
    return result


def _install_adapter(ns, options):
    original = ns["_variant_original_selector"]
    original_select = ns["_variant_original_select_context"]
    original_rank = ns["_variant_original_rank_tfidf"]

    # Clone only CTS method globals. Rebinding question_features in the whole
    # notebook would also change RuleRouter, invalidating E2's control.
    constant_globals = dict(ns, question_features=lambda question: np.array([1., 1., 0.]))
    constant_choose = FunctionType(original.choose.__code__, constant_globals)
    constant_update = FunctionType(original.update.__code__, constant_globals)

    class ExperimentalSelector(original):
        def __init__(self, method, seed, cfg):
            validate_config(cfg)
            super().__init__(method, seed, cfg)
            self.selected_counts = np.zeros(len(ARMS), dtype=int)
            self.refit_counts = np.zeros(len(ARMS), dtype=int)
            self.refit_seconds = np.zeros(len(ARMS), dtype=float)
            ns["_variant_last_selector"] = self

        def choose(self, question, costs):
            if self.method == "LaplaceCTS" and options["feature_mode"] == "constant":
                return constant_choose(self, question, costs)
            return super().choose(question, costs)

        def update(self, arm_index, reward, question):
            due = (self.method == "LaplaceCTS" and 0 <= arm_index < len(ARMS)
                   and (len(self.rewards[arm_index]) + 1) % self.refit_every == 0)
            start = perf_counter()
            if self.method == "LaplaceCTS" and options["feature_mode"] == "constant":
                constant_update(self, arm_index, reward, question)
            else:
                super().update(arm_index, reward, question)
            self.selected_counts[arm_index] += 1
            if due:
                self.refit_counts[arm_index] += 1
                self.refit_seconds[arm_index] += perf_counter() - start

    def rank(view, resolved=False):
        if not resolved or (options["resolve_pronouns"] and options["normalize_aliases"]):
            return original_rank(view, resolved=resolved)
        history, question = view["history"], view["question"]
        explicit = ns["M2_PROJECT"].search(question)
        project = explicit.group().upper() if explicit else None
        if project is None and re.search(r"\bits\b", question, re.I):
            if options["resolve_pronouns"]:
                for message in history:
                    focus = ns["M2_FOCUS"].search(message["text"])
                    if focus:
                        project = focus.group(1).upper()
            else:
                project = "its"
        # With alias normalization disabled, preserve the surface attribute in
        # BOTH query and index; reader normalization remains untouched.
        alias_map = {term: canonical for canonical, alias in ns["M2_ALIASES"].items()
                     for term in (canonical, alias)}
        attribute = next((term for term in sorted(alias_map, key=len, reverse=True)
                          if re.search(r"\b" + re.escape(term) + r"\b", question, re.I)), None)
        if attribute and options["normalize_aliases"]:
            attribute = alias_map[attribute]
        query = " ".join(part for part in (project, attribute) if part)
        documents = [{"id": message["id"], "text": (
            ns["m2_normalize"](message["text"]) if options["normalize_aliases"] else message["text"])}
            for message in history]
        return original_rank({"history": documents, "question": query}, resolved=False)

    def select(view, arm, cfg):
        default_retrieval = all(options[key] == DEFAULT_ADAPTER[key] for key in (
            "resolved_top_k", "resolve_pronouns", "normalize_aliases", "preserve_focus"))
        if arm != "resolved_tfidf" or default_retrieval:
            return original_select(view, arm, cfg)
        if set(view) != {"question", "history"}:
            raise ValueError("Public view must contain only question/history")
        history = view["history"]
        ns["m2_validate_history"](history)
        budget = cfg["budgets"][arm]
        if type(budget) is not int or budget < 0:
            raise ValueError("Context budget must be a nonnegative integer")
        if not history or budget == 0:
            return []
        positions = rank(view, resolved=True)["position"].head(options["resolved_top_k"]).tolist()
        if (options["preserve_focus"] and not ns["M2_PROJECT"].search(view["question"])
                and re.search(r"\bits\b", view["question"], re.I)):
            anchors = [i for i, message in enumerate(history) if ns["M2_FOCUS"].search(message["text"])]
            if anchors:
                anchor = anchors[-1]
                if ns["count_input_units"](history[anchor]["text"]) > budget:
                    return []
                positions = [anchor] + [i for i in positions if i != anchor]
        return ns["m2_pack_messages"](history, positions, budget)

    ns["Selector"] = ExperimentalSelector
    ns["m2_rank_tfidf"] = rank
    ns["select_context"] = select
    ns["_variant_options"] = deepcopy(options)


def evaluate_episodes(ns, episodes, cfg):
    """Audit and construct all four arms; construction timings are newly measured."""
    validate_config(cfg)
    episodes = list(episodes)
    if not episodes:
        raise ValueError("At least one episode is required")
    keys = [(episode["scenario"], episode["seed"]) for episode in episodes]
    if len(keys) != len(set(keys)):
        raise ValueError("Duplicate episode")
    frames = []
    for episode in episodes:
        if len(episode["probes"]) != cfg["T"]:
            raise ValueError("Episode length differs from cfg.T")
        if not ns["audit_truth"](episode)["passed"]:
            raise ValueError("Independent truth audit failed")
        frames.append(ns["evaluate_episode"](episode, cfg))
    return pd.concat(frames, ignore_index=True)


def replay_all(ns, outcomes, cfg):
    """Return (complete seven-method replay, per-arm selection/refit diagnostics).

    Each scenario must be present. Diagnostics count only successful updates; an
    optimizer error propagates to the runner, which records the failed attempt.
    Refitting elapsed time covers the update call on refit rounds and is not API
    latency or part of the utility objective. trajectory_seconds is repeated on
    four arm rows: take one value per scenario/seed/method/alg_seed, not their sum.
    """
    validate_config(cfg)
    seeds = {scenario: sorted(map(int, group.seed.unique()))
             for scenario, group in outcomes.groupby("scenario")}
    validate_outcomes(outcomes, cfg, seeds)
    frames, records = [], []
    for (scenario, seed), group in outcomes.groupby(["scenario", "seed"], sort=True):
        for method in METHODS:
            for alg_seed in cfg["algorithm_seeds"]:
                start = perf_counter()
                frame = ns["replay_episode"](group, method, alg_seed, cfg)
                elapsed = perf_counter() - start
                selector = ns["_variant_last_selector"]
                frames.append(frame)
                for index, arm in enumerate(ARMS):
                    records.append({
                        "scenario": scenario, "seed": int(seed), "method": method,
                        "alg_seed": alg_seed, "arm": arm,
                        "selected_count": int(selector.selected_counts[index]),
                        "refit_count": int(selector.refit_counts[index]),
                        "refit_seconds": float(selector.refit_seconds[index]),
                        "trajectory_seconds": elapsed,
                        "prior_precision": cfg["prior_precision"],
                        "refit_every": cfg["refit_every"],
                        "feature_mode": ns["_variant_options"]["feature_mode"],
                    })
    replay = pd.concat(frames, ignore_index=True)
    validate_replay(replay, outcomes, cfg)
    return replay, pd.DataFrame(records)
