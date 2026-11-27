"""Small, in-memory interface smoke tests; not formal acceptance or a sandbox."""
import argparse
import ast
from copy import deepcopy
import json
from pathlib import Path
import sys
import traceback

ROOT = Path(__file__).resolve().parents[1]


def load(notebook, member):
    # Deliberately skip executable walkthroughs, setup/install and export cells.
    # Keep imports, declarations and module constants in the selected section.
    import numpy as np
    import pandas as pd
    ns = dict(np=np, pd=pd)
    cells = json.loads(notebook.read_text(encoding="utf-8"))["cells"]
    protocol = next(c for c in cells if c.get("id") == "shared-protocol-draft")
    exec(compile("".join(protocol["source"]), "shared-protocol-draft", "exec"), ns)
    prefixes = ("m1-", "m2-") if member == "m2" else (member + "-",)
    for cell in cells:
        if cell.get("cell_type") != "code" or not cell.get("id", "").startswith(prefixes):
            continue
        tree = ast.parse("".join(cell["source"]))
        tree.body = [node for node in tree.body if isinstance(node, (
            ast.Import, ast.ImportFrom, ast.FunctionDef, ast.AsyncFunctionDef,
            ast.ClassDef, ast.Assign, ast.AnnAssign))]
        exec(compile(tree, cell["id"], "exec"), ns)
    return ns


def check(condition, message):
    if not condition:
        raise AssertionError(message)


def m1(ns):
    cfg = dict(ns["PROTOCOL_DRAFT"], T=8)
    for scenario in ns["SCENARIOS"]:
        ep = ns["generate_episode"](910001, scenario, cfg)
        check(ep == ns["generate_episode"](910001, scenario, cfg), "same seed not reproducible")
        check(len(ep["probes"]) == 8, "expected 8 probes")
        check([m["id"] for m in ep["history"]] == list(range(len(ep["history"]))), "message IDs")
        check([p["t"] for p in ep["probes"]] == list(range(8)), "probe IDs")
        for p in ep["probes"]:
            view = ns["public_view"](ep, p)
            check(set(view) == {"question", "history"}, "hidden fields exposed")
            check(view["history"] == ep["history"][:p["end"]], "incorrect history prefix")
            check(0 <= p["evidence"] < p["end"], "future evidence")
            check(p["state"] == ("B" if scenario == "abrupt" and p["t"] >= 4 else "A"), "switch boundary")
        changed = deepcopy(ep)
        changed["history"].append(dict(id=len(ep["history"]), text="future fixture"))
        check(ns["public_view"](changed, ep["probes"][0]) == ns["public_view"](ep, ep["probes"][0]), "future leak")
        ns["audit_truth"](ep)  # Return schema is implementation-specific; not a pass verdict.


def m2(ns):
    cfg = ns["PROTOCOL_DRAFT"]
    history = [dict(id=0, text="Focus is project P1."),
               dict(id=1, text="For project P1: the dataset is V10.")]
    q = "What is P1 current dataset?"
    view = dict(question=q, history=history)
    for arm in ns["ARMS"]:
        original = deepcopy(view)
        context = ns["select_context"](view, arm, cfg)
        ids = [m["id"] for m in context]
        check(ids == sorted(set(ids)), "context IDs not unique/sorted")
        check(all(m in history for m in context), "context outside public history")
        check(ns["count_input_units"]("\n".join(m["text"] for m in context)) <= cfg["budgets"][arm], "over budget")
        check(view == original, "input mutated")
        check(ns["rule_reader"](q, context) == "V10", "tiny factual answer")
    check(ns["rule_reader"](q, []) == "UNKNOWN", "empty context answer")
    ep = dict(seed=910002, scenario="stable", history=history, probes=[dict(
        t=0, question=q, end=2, gold="V10", evidence=1, old_values=[], qtype="recent", state="A")])
    frame = ns["evaluate_episode"](ep, cfg)
    check(len(frame) == 4 and set(frame.arm) == set(ns["ARMS"]), "four-arm rows")
    check(not frame.duplicated(["seed", "t", "arm"]).any(), "duplicate keys")
    check(ns["np"].allclose(frame.utility, frame.y - cfg["lambda"] * frame.cost / cfg["cost_reference"]), "utility formula")


def m3(ns):
    np, pd = ns["np"], ns["pd"]
    cfg = ns["PROTOCOL_DRAFT"]
    check(np.allclose(ns["question_features"]("What is its current dataset?"), [1, 0, 1]), "its features")
    rows = [dict(seed=910003, scenario="stable", t=t, arm=a,
                 question="What is P1 current dataset?", y=(t+k)%2, cost=20+k,
                 utility=(t+k)%2-.5*(20+k)/512, coverage=1, outdated=0)
            for t in range(12) for k, a in enumerate(ns["ARMS"])]
    frame = pd.DataFrame(rows)
    for method in list(ns["ARMS"]) + ["TS", "LaplaceCTS", "RuleRouter"]:
        result = ns["replay_episode"](frame.copy(), method, 17, cfg)
        again = ns["replay_episode"](frame.copy(), method, 17, cfg)
        pd.testing.assert_frame_equal(result, again)
        check(len(result) == 12 and set(result.t) == set(range(12)), "incomplete replay")
        check(set(result.method) == {method} and set(result.alg_seed) == {17}, "replay metadata")
        check(set(result.seed) == {910003} and set(result.scenario) == {"stable"}, "dialogue metadata")
        for row in result.itertuples():
            source = frame[(frame.t == row.t) & (frame.arm == row.arm)].iloc[0]
            for metric in ["y", "cost", "utility", "coverage", "outdated"]:
                check(np.isclose(getattr(row, metric), source[metric]), "selected outcome mismatch")
        if method in ns["ARMS"]:
            check(set(result.arm) == {method}, "fixed arm changed")
        altered = frame.copy()
        selected = dict(zip(result.t, result.arm))
        mask = altered.apply(lambda r: r.arm != selected[r.t], axis=1)
        altered.loc[mask, "y"] = 1-altered.loc[mask, "y"]
        altered["utility"] = altered.y-.5*altered.cost/512
        pd.testing.assert_frame_equal(result, ns["replay_episode"](altered, method, 17, cfg))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--member", choices=["m1", "m2", "m3", "all"], default="all")
    parser.add_argument("--notebook", type=Path, default=ROOT / "ARIN7101_Context_Bandit_Release_Notebook.ipynb")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()
    statuses = []
    for member in (["m1", "m2", "m3"] if args.member == "all" else [args.member]):
        try:
            ns = load(args.notebook, member)
            globals()[member](ns)
        except NotImplementedError as exc:
            print(f"[NOT_READY] {member}: {exc}")
            statuses.append(2)
        except Exception as exc:
            print(f"[FAIL] {member}: {type(exc).__name__}: {exc}")
            if args.verbose:
                traceback.print_exc()
            statuses.append(1)
        else:
            print(f"[PASS] {member}: small interface fixture only")
            statuses.append(0)
    print("No formal results or human acceptance. Review full member tests separately.")
    return 1 if 1 in statuses else (2 if 2 in statuses else 0)


if __name__ == "__main__":
    sys.exit(main())
