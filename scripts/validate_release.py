"""Check notebook structure, not research correctness or task completion."""
import argparse
import ast
import json
from pathlib import Path

import nbformat

ROOT = Path(__file__).resolve().parents[1]
NOTEBOOK = ROOT / "ARIN7101_Context_Bandit_Release_Notebook.ipynb"
STAGES = ["setup", "m1", "m2", "m3", "m4", "m5", "wrapup"]


def is_stub(node):
    body = list(node.body)
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) and isinstance(body[0].value.value, str):
        body = body[1:]
    return (len(body) == 1 and isinstance(body[0], ast.Raise)
            and isinstance(body[0].exc, ast.Call)
            and isinstance(body[0].exc.func, ast.Name)
            and body[0].exc.func.id == "NotImplementedError")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expect-scaffold", action="store_true",
                        help="Check the initial distribution contains only unimplemented research interfaces.")
    args = parser.parse_args()
    notebook = nbformat.read(NOTEBOOK, as_version=4)
    nbformat.validate(notebook)
    ids = [cell.id for cell in notebook.cells]
    assert len(ids) == len(set(ids)), "Duplicate cell IDs"
    order = []
    pending = {member: [] for member in STAGES[1:-1]}
    definitions = {member: [] for member in STAGES[1:-1]}
    for cell in notebook.cells:
        tags = cell.metadata.get("tags", [])
        assert len(tags) == 1 and tags[0] in STAGES, f"Invalid stage tag: {cell.id}"
        stage = tags[0]
        order.append(STAGES.index(stage))
        if cell.cell_type != "code":
            continue
        assert not cell.outputs and cell.execution_count is None, "Clear notebook outputs before committing"
        tree = ast.parse(cell.source, filename=cell.id)
        if stage not in definitions:
            continue
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                definitions[stage].append(node.name)
                if is_stub(node):
                    pending[stage].append(node.name)
                if args.expect_scaffold:
                    assert is_stub(node), f"Research implementation already supplied: {cell.id}/{node.name}"
        if args.expect_scaffold:
            # Member cells may define empty interfaces, but cannot run hidden solutions.
            assert all(isinstance(node, (ast.FunctionDef, ast.ClassDef)) for node in tree.body), cell.id
            for node in tree.body:
                if isinstance(node, ast.ClassDef):
                    assert all(isinstance(child, ast.FunctionDef) for child in node.body), cell.id
    assert order == sorted(order) and set(order) == set(range(len(STAGES))), "Task sections missing or out of order"
    for member in definitions:
        assert definitions[member], f"Missing interfaces for {member}"
        assert f"member-{member}" in ids
        assert (ROOT / "deliverables" / f"{member.upper()}_notes.md").is_file()
    for filename in ["README.md", "docs/TEAM_WORKFLOW.md", "docs/OUTPUT_CONTRACT.md",
                     "team_workspace/team_progress.csv", "team_workspace/interface_decisions.md",
                     "team_workspace/formal_runs.json"]:
        assert (ROOT/filename).is_file(), filename
    assert isinstance(json.loads((ROOT/"team_workspace/formal_runs.json").read_text(encoding="utf-8")), list)
    print(f"STRUCTURE PASS: {len(notebook.cells)} cells; valid schema/syntax, ordered task sections, clean outputs.")
    for member, names in pending.items():
        print(f"{member.upper()}: {len(names)} unimplemented interfaces: {', '.join(names)}")
    if args.expect_scaffold:
        assert all(pending.values()), "Each member must retain meaningful implementation work"
        print("INITIAL SCAFFOLD PASS: member code contains only unimplemented interfaces.")
    print("This check does NOT validate algorithms, experiments, findings, or member completion.")


if __name__ == "__main__":
    main()
