"""No dialogue generation: small files exercise the seed-inventory boundaries."""
import json
from pathlib import Path
import tempfile
import unittest

from m4_seed_inventory import collect_seed_inventory


class SeedInventoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='m4_seed_inventory_')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def write(self, path, data):
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(data if isinstance(data, str) else json.dumps(data), encoding='utf-8')

    def test_algorithm_and_bootstrap_seeds_are_not_dialogues(self):
        self.write('outputs/demo/a/manifest.json', dict(seeds=dict(dialogue=[41, 43], algorithm=[17, 37]),
            config=dict(algorithm_seeds=[17, 37], bootstrap_seed=2026)))
        self.write('docs/analysis.md', 'bootstrap: 2000 draws, seed=2026\nalgorithm seed=17\n算法种子 seed=37\n')
        result = collect_seed_inventory(self.root)
        self.assertEqual(result['known_used_seeds'], [41, 43])

    def test_candidate_plans_do_not_pollute_inventory(self):
        candidates = collect_seed_inventory(self.root)['candidate_seeds']
        self.write('outputs/development/x/plan_draft.json', dict(evaluation_seeds=candidates))
        self.write('outputs/frozen/example/frozen_config.json', dict(plan=dict(evaluation_seeds=candidates)))
        self.write('deliverables/m4_formal_preparation_example/seed_inventory.json', dict(candidate_seeds=candidates))
        self.write('deliverables/other.json', dict(evaluation_seeds=candidates))
        self.write('docs/proposed.md', '候选正式seed=' + str(candidates['stable'][0]))
        result = collect_seed_inventory(self.root)
        self.assertEqual(result['known_used_seeds'], [])
        self.assertEqual(result['collisions'], [])

    def test_actual_started_or_failed_registry_is_excluded(self):
        candidate = collect_seed_inventory(self.root)['candidate_seeds']['stable'][0]
        self.write('team_workspace/formal_runs.json', [
            dict(status='started', evaluation_seeds=[candidate]),
            dict(status='failed', evaluation_seeds=[candidate + 1]),
            dict(status='planned', evaluation_seeds=[candidate + 2]),
        ])
        result = collect_seed_inventory(self.root)
        self.assertEqual(result['collisions'], [candidate, candidate + 1])

    def test_csv_reads_seed_column_only(self):
        self.write('outputs/demo/x/table.csv', 'seed,alg_seed,cost,bootstrap_seed\n61,17,2026,2026\n61,37,512,2026\n')
        result = collect_seed_inventory(self.root)
        self.assertEqual(result['known_used_seeds'], [61])
        self.assertEqual(len(result['sources'][0]['sha256']), 64)

    def test_literal_fixture_ranges_and_generator_arguments(self):
        source = ('generate_episode(31415, "stable", cfg)\n'
                  'fixture = dict(seed=7, alg_seed=17)\n'
                  'plan = dict(evaluation_seeds=dict(stable=list(range(810000,810002))))\n'
                  'bootstrap_seed = 2026\n')
        self.write('scripts/test_example.py', source)
        result = collect_seed_inventory(self.root)
        self.assertEqual(result['known_used_seeds'], [7, 31415, 810000, 810001])

    def test_parse_failures_are_reported(self):
        self.write('outputs/development/bad.json', '{invalid')
        result = collect_seed_inventory(self.root)
        self.assertEqual(len(result['extraction_errors']), 1)
        self.assertEqual(result['extraction_errors'][0]['path'], 'outputs/development/bad.json')
        self.assertEqual(result['scan_errors'], result['extraction_errors'])


if __name__ == '__main__':
    unittest.main()
