"""Read-only audit of visible dialogue seeds; never imports a generator.

Recorded data and literal fixtures are conservatively excluded. Candidate
plans are not observations. Algorithm/bootstrap RNG seeds are separate axes.
"""
import argparse
import ast
import csv
import gzip
import hashlib
import io
import json
from pathlib import Path
import re
import zipfile


def _sha(content):
    return hashlib.sha256(content).hexdigest()


def _integers(value):
    if type(value) is int:
        return {value} if value >= 0 else set()
    if isinstance(value, (list, tuple, set)):
        return set().union(*(_integers(v) for v in value)) if value else set()
    if isinstance(value, dict):
        return set().union(*(_integers(v) for v in value.values())) if value else set()
    return set()


def _literal(node):
    """Small non-executing evaluator for literal fixtures and range/list calls."""
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        return [_literal(x) for x in node.elts]
    if isinstance(node, ast.Dict):
        return {_literal(k): _literal(v) for k, v in zip(node.keys, node.values) if k is not None}
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
        if node.func.id == 'dict':
            return {kw.arg: _literal(kw.value) for kw in node.keywords if kw.arg}
        args = [_literal(arg) for arg in node.args]
        if node.func.id == 'range' and all(type(arg) is int for arg in args):
            values = range(*args)
            if len(values) > 10000:
                raise ValueError('Seed literal range exceeds audit limit')
            return list(values)
        if node.func.id in ('list', 'tuple', 'set') and len(args) == 1:
            return args[0]
    raise ValueError('Nonliteral expression')


def _source_seeds(text, fixture=False):
    tree = ast.parse(text)
    seeds, unresolved = set(), []
    def take(node):
        try:
            seeds.update(_integers(_literal(node)))
        except (ValueError, TypeError):
            pass
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            name = node.func.id if isinstance(node.func, ast.Name) else ''
            if name in ('generate_episode', 'generate') and node.args:
                try:
                    value = _literal(node.args[0])
                    seeds.update(_integers(value))
                except (ValueError, TypeError):
                    unresolved.append(dict(line=node.lineno, expression=ast.unparse(node.args[0])))
            if name == 'dict':
                for kw in node.keywords:
                    if kw.arg in ('seed', 'dev_seed', 'demo_seed', 'dialogue_seeds'):
                        take(kw.value)
                    elif fixture and kw.arg == 'evaluation_seeds':
                        take(kw.value)
        elif isinstance(node, ast.Dict):
            for key, value in zip(node.keys, node.values):
                if isinstance(key, ast.Constant) and key.value in ('seed', 'dev_seed', 'demo_seed', 'dialogue_seeds'):
                    take(value)
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                name = target.id if isinstance(target, ast.Name) else target.attr if isinstance(target, ast.Attribute) else ''
                if name in ('seed', 'dev_seed', 'demo_seed') or (fixture and name in ('seeds', 'evaluation_seeds')):
                    take(node.value)
        elif isinstance(node, (ast.For, ast.comprehension)):
            target = node.target
            if isinstance(target, ast.Name) and target.id == 'seed':
                take(node.iter)
    return seeds, unresolved


def _json_seeds(value):
    seeds = set()
    if isinstance(value, list):
        for item in value:
            seeds.update(_json_seeds(item))
    elif isinstance(value, dict):
        for key, item in value.items():
            if key in ('algorithm_seeds', 'algorithm', 'alg_seed', 'algorithm_seed', 'bootstrap_seed',
                       'evaluation_seeds', 'formal_seed', 'candidate_seeds', 'proposed_seeds'):
                continue
            if key == 'seed':
                seeds.update(_integers(item))
            elif key in ('dialogue_seeds', 'used_seeds'):
                seeds.update(_integers(item))
            elif key == 'seeds' and isinstance(item, dict):
                for category in ('dialogue', 'development', 'evaluation'):
                    seeds.update(_integers(item.get(category, [])))
            else:
                seeds.update(_json_seeds(item))
    return seeds


def _csv_seeds(text):
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames or 'seed' not in reader.fieldnames:
        return set()
    seeds = set()
    for row in reader:
        value = row.get('seed', '').strip()
        if value:
            if not re.fullmatch(r'\d+', value):
                raise ValueError('Noninteger dialogue seed in CSV: ' + value)
            seeds.add(int(value))
    return seeds


def _excluded_path(relative):
    parts = Path(relative.replace('\\', '/')).parts
    lower = relative.lower()
    return (any(p.lower().startswith('m4_formal_preparation') for p in parts)
            or ('outputs' in parts and 'frozen' in parts)
            or Path(relative).name.lower().startswith(('plan', 'frozen_config', 'approval', 'seed_inventory'))
            or Path(relative).name in ('m4_seed_inventory.py', 'test_m4_seed_inventory.py')
            or '__pycache__' in parts
            or lower.endswith(('.pyc', '.png', '.svg', '.pdf')))


def collect_seed_inventory(root):
    """Return a reproducible local inventory plus 60 unexecuted candidate seeds."""
    root = Path(root).resolve()
    sources, errors, unresolved, skipped = [], [], [], []
    known = set()
    def add(path, content, category, seeds, detail=None):
        if seeds:
            seeds = sorted(seeds)
            known.update(seeds)
            record = dict(path=path, category=category, sha256=_sha(content), seeds=seeds)
            if detail:
                record['detail'] = detail
            sources.append(record)
    def inspect(relative, content):
        if _excluded_path(relative):
            skipped.append(relative)
            return
        suffix = Path(relative).suffix.lower()
        try:
            if suffix == '.csv':
                add(relative, content, 'recorded_csv_dialogue_seed', _csv_seeds(content.decode('utf-8-sig')))
            elif relative.endswith('.jsonl.gz'):
                records = [json.loads(line) for line in gzip.decompress(content).decode('utf-8-sig').splitlines() if line.strip()]
                add(relative, content, 'recorded_dialogue_archive', _json_seeds(records))
            elif suffix == '.json':
                data = json.loads(content.decode('utf-8-sig'))
                if Path(relative).name == 'formal_runs.json':
                    if not isinstance(data, list):
                        raise ValueError('Formal registry must be a list')
                    seeds = set()
                    for event in data:
                        if event.get('status') in ('started', 'failed', 'computed_pending_review', 'complete'):
                            seeds.update(_integers(event.get('evaluation_seeds', [])))
                            seeds.update(_integers(event.get('dialogue_seeds', [])))
                    # Preserve even the empty registry as affirmative checked evidence.
                    sources.append(dict(path=relative, category='formal_attempt_registry', sha256=_sha(content), seeds=sorted(seeds)))
                    known.update(seeds)
                else:
                    add(relative, content, 'recorded_json_dialogue_seed', _json_seeds(data))
            elif suffix == '.py':
                fixture = Path(relative).name.startswith('test_')
                seeds, pending = _source_seeds(content.decode('utf-8-sig'), fixture=fixture)
                add(relative, content, 'literal_fixture_or_generator_argument', seeds)
                unresolved.extend(dict(path=relative, **item) for item in pending)
            elif suffix == '.ipynb':
                notebook = json.loads(content.decode('utf-8-sig'))
                seeds = set()
                for index, cell in enumerate(notebook.get('cells', [])):
                    if cell.get('cell_type') == 'code':
                        src = cell.get('source', '')
                        src = ''.join(src) if isinstance(src, list) else src
                        label = relative + '#' + cell.get('id', str(index))
                        try:
                            found, pending = _source_seeds(src, fixture=True)
                            seeds.update(found)
                            unresolved.extend(dict(path=label, **item) for item in pending)
                        except SyntaxError as exc:
                            unresolved.append(dict(path=label, reason='Non-Python/magic cell not parsed', line=exc.lineno))
                        for output in cell.get('outputs', []):
                            text = output.get('text', '')
                            text = ''.join(text) if isinstance(text, list) else text
                            seeds.update(int(v) for v in re.findall(r'\bseed=(\d+)\b', text))
                add(relative, content, 'notebook_literals_or_recorded_execution_output', seeds)
            elif suffix == '.zip':
                with zipfile.ZipFile(io.BytesIO(content)) as archive:
                    for info in archive.infolist():
                        if not info.is_dir() and info.filename.endswith(('.json', '.csv', '.jsonl.gz', '.ipynb')):
                            inspect(relative + '!' + info.filename, archive.read(info))
            elif suffix == '.md':
                # Human notes can supply an explicitly labelled one-off seed.
                lines = [line for line in content.decode('utf-8-sig').splitlines()
                         if 'bootstrap' not in line.lower() and 'algorithm' not in line.lower()
                         and not re.search(r'算法\s*(?:seed|种子)|候选|拟选|拟定|尚未使用|待冻结', line)
                         and 'candidate' not in line.lower() and 'proposed' not in line.lower()]
                seeds = {int(v) for line in lines
                         for v in re.findall(r'(?<![\w])(?:seed|seed值)\s*[=:：]\s*(\d+)\b', line)}
                add(relative, content, 'documented_literal_seed', seeds)
        except (OSError, ValueError, TypeError, KeyError, SyntaxError, UnicodeError, zipfile.BadZipFile) as exc:
            errors.append(dict(path=relative, error=type(exc).__name__ + ': ' + str(exc)))

    paths = []
    for folder in ('scripts', 'reference', 'team_workspace', 'deliverables', 'outputs', 'docs'):
        if (root / folder).exists():
            paths.extend(p for p in (root / folder).rglob('*') if p.is_file())
    paths.extend(p for p in root.glob('*.ipynb') if p.is_file())
    paths.extend(p for p in root.glob('*.md') if p.is_file())
    for path in sorted(set(paths)):
        relative = path.relative_to(root).as_posix()
        if _excluded_path(relative):
            skipped.append(relative)
            continue
        if path.suffix.lower() in ('.csv', '.json', '.py', '.ipynb', '.zip', '.md') or path.name.endswith('.jsonl.gz'):
            try:
                inspect(relative, path.read_bytes())
            except OSError as exc:
                errors.append(dict(path=relative, error=str(exc)))

    # Audited protocol ranges include dynamic generator offsets that a literal
    # AST pass cannot evaluate. Bind each rule to its visible repository source.
    conservative = [
        ('scripts/m4_protocol.py', 'protocol_reserved_reference_and_known_runs',
         set(range(20261105, 20261135)) | set(range(20261205, 20261235))
         | set(range(130000, 130003)) | set(range(130100, 130103))
         | set(range(730000, 730006)) | set(range(730100, 730106))
         | {42, 910001, 910002, 910003, 910010}),
    ]
    for relative, category, seeds in conservative:
        path = root / relative
        if path.exists():
            add(relative, path.read_bytes(), category, seeds,
                'Conservative manual rule for current repository; reference ranges and dynamic +100 scenario offsets')
    candidates = dict(stable=list(range(930000, 930030)), abrupt=list(range(930100, 930130)))
    proposed = {s for group in candidates.values() for s in group}
    dev_range = set(range(130000, 130003)) | set(range(130100, 130103))
    historical_eval = set(range(730000, 730006)) | set(range(730100, 730106))
    historical_eval |= set(range(20261105, 20261135)) | set(range(20261205, 20261235))
    resolutions = []
    for item in unresolved:
        expression = item.get('expression', '')
        if 'dev_seed' in expression:
            covered = dev_range
            category = 'configured_development_offset'
        elif "CFG['eval_seed']" in expression and item['path'].startswith('reference/'):
            covered = historical_eval
            category = 'historical_reference_evaluation_offset'
        else:
            covered = set()
            category = 'unrecognized_expression'
        evidence_sources = [record['path'] for record in sources
                            if covered and covered.issubset(set(record['seeds']))
                            and record['category'] in ('protocol_reserved_reference_and_known_runs',
                                'recorded_json_dialogue_seed', 'recorded_csv_dialogue_seed',
                                'recorded_dialogue_archive', 'notebook_literals_or_recorded_execution_output')]
        status = 'visible_run_values_covered' if covered and covered.issubset(known) and evidence_sources else 'human_review_required'
        resolutions.append(dict(**item, category=category, status=status, covered_seeds=sorted(covered),
            evidence_sources=sorted(set(evidence_sources)),
            limitation='Covers visible default/archived runs only; arbitrary runtime overrides and unshared runs require disclosure.'))
    return dict(schema_version=1, root=str(root), known_used_seeds=sorted(known), sources=sources,
        candidate_seeds=candidates, collisions=sorted(known & proposed), extraction_errors=errors, scan_errors=errors,
        unresolved_seed_expressions=unresolved, skipped_proposal_paths=sorted(set(skipped)),
        dynamic_expression_resolution=resolutions,
        dynamic_expression_summary=dict(total=len(resolutions),
            visible_run_values_covered=sum(item['status'] == 'visible_run_values_covered' for item in resolutions),
            human_review_required=sum(item['status'] == 'human_review_required' for item in resolutions)),
        formal_data_generated=False, candidate_selection='Fixed numerical ranges chosen before generating outcomes; no generator called',
        limitations=[
            'Only this workspace and visible archive contents were inspected; unshared teammate runs require human disclosure.',
            'Literal fixture IDs are conservatively excluded even if only defined in tests; exclusion is not a claim that research dialogues were generated.',
            'Algorithm RNG seeds and bootstrap RNG seeds are excluded from dialogue-seed extraction.',
            'Dynamic seed expressions are listed separately and supplemented by archived data and explicit protocol ranges; human review remains required.',
            'Preparation directories, draft plans, frozen plans and candidate inventories are not observations and do not contaminate the used set.',
        ])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    print(json.dumps(collect_seed_inventory(args.root), ensure_ascii=False, indent=2))
