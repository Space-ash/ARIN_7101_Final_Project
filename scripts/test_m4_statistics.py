"""Mathematical fixtures for A1-A6; no dialogue generation or formal writes."""
import unittest

import numpy as np
import pandas as pd
from scipy import integrate, stats

from m4_analysis import METHODS, SCENARIOS
from m4_statistics import (bootstrap_interval, holm_adjust, paired_t, rope_probabilities,
                           sign_flip, sign_test, statistical_analysis, wilcoxon_test)


class StatisticsTests(unittest.TestCase):
    def setUp(self):
        self.cfg = dict(T=300, algorithm_seeds=[17, 37], **{"lambda": .5},
                        cost_reference=512, n_bootstrap=2000, bootstrap_seed=2026)
        self.baselines = dict(stable="recent_short", abrupt="resolved_tfidf")
        rows = []
        for si, scenario in enumerate(SCENARIOS):
            for d in range(4):
                for m, method in enumerate(METHODS):
                    y = .3 + .03 * m + .01 * d * (m % 3)
                    cost = 64 + 4 * m
                    rows.append(dict(scenario=scenario, seed=100 + 100 * si + d,
                                     method=method, y=y, cost=cost, utility=y-cost/1024,
                                     coverage=y, outdated=.1))
        self.metrics = pd.DataFrame(rows)
        self.rope = dict(mu_prior_sd=.1, sigma_prior_shape=2., sigma_prior_scale=.01, delta=.02)

    def test_percentile_constant_and_bca_undefined(self):
        result = bootstrap_interval([.1, .1, .1], 100)
        self.assertEqual(result["low"], .1)
        self.assertEqual(result["high"], .1)
        self.assertEqual(result["status"], "degenerate_constant_sample")
        bca = bootstrap_interval([.1, .1, .1], 100, "BCa")
        self.assertEqual(bca["status"], "undefined_degenerate_bca")
        self.assertTrue(np.isnan(bca["low"]))

    def test_bootstrap_reproducible_and_bca_finite(self):
        values = np.array([-.2, -.1, .02, .08, .3])
        a = bootstrap_interval(values, 1000, "BCa", seed=7)
        b = bootstrap_interval(values, 1000, "BCa", seed=7)
        self.assertEqual(a, b)
        self.assertEqual(a["status"], "ok")
        self.assertLess(a["low"], values.mean())
        self.assertGreater(a["high"], values.mean())

    def test_t_hand_calculation_and_degeneracy(self):
        result = paired_t([1., 2., 3.])
        self.assertAlmostEqual(result["statistic"], 2*np.sqrt(3))
        self.assertAlmostEqual(result["p_value"], stats.ttest_1samp([1, 2, 3], 0).pvalue)
        self.assertAlmostEqual(result["low"], 2-stats.t.ppf(.975, 2)/np.sqrt(3))
        for values, status in [([0, 0, 0], "degenerate_zero"), ([.1, .1, .1], "degenerate_nonzero")]:
            r = paired_t(values)
            self.assertEqual(r["status"], status)
            self.assertTrue(np.isnan(r["p_value"]))

    def test_sign_frequency_differs_from_mean_and_ties(self):
        result = sign_test([.01, .01, .01, -1, 0])
        self.assertEqual((result["wins"], result["losses"], result["ties"]), (3, 1, 1))
        self.assertEqual(result["conditional_win_rate"], .75)
        self.assertEqual(result["p_value"], .625)
        self.assertTrue(np.isnan(sign_test([0, 0])["conditional_win_rate"]))
        self.assertEqual(sign_test([1e-14, -.2], tie_tolerance=1e-12)["ties"], 1)

    def test_sign_flip_exact_and_monte_carlo(self):
        exact = sign_flip([1., 2., 3.])
        self.assertEqual(exact["resamples"], 8)
        self.assertEqual(exact["p_value"], .25)
        self.assertEqual(sign_flip([0, 0])["p_value"], 1)
        mc = sign_flip([1, 2, 3], resamples=5000, seed=12, exact_max_n=0)
        self.assertEqual(mc, sign_flip([1, 2, 3], resamples=5000, seed=12, exact_max_n=0))
        self.assertLess(abs(mc["p_value"]-.25), .03)
        self.assertGreater(mc["p_value"], 0)

    def test_wilcoxon_exact_ties_and_zero(self):
        result = wilcoxon_test([1., 2., 3.], tie_tolerance=0)
        self.assertEqual(result["calculation"], "exact")
        self.assertEqual(result["p_value"], .25)
        self.assertEqual(wilcoxon_test([0., 0.])["p_value"], 1)
        tied = wilcoxon_test([.1, .1, -.1, 0])
        self.assertEqual(tied["calculation"], "approx")
        self.assertTrue(np.isfinite(tied["p_value"]))

    def test_holm_known_family_and_invalid_values(self):
        np.testing.assert_allclose(holm_adjust([.01, .04, .03]), [.03, .06, .06])
        np.testing.assert_allclose(holm_adjust([.9, .9, 1]), [1, 1, 1])
        with self.assertRaises(ValueError):
            holm_adjust([.01, np.nan])

    def test_rope_symmetric_normalizes_and_sign_reversal(self):
        zero = rope_probabilities([-.02, -.01, .01, .02], **self.rope)
        self.assertAlmostEqual(zero["p_gain"], zero["p_loss"], places=10)
        self.assertAlmostEqual(sum(zero[k] for k in ["p_gain", "p_equivalent", "p_loss"]), 1, places=9)
        positive = rope_probabilities([.08, .1, .12, .14], **self.rope)
        negative = rope_probabilities([-.08, -.1, -.12, -.14], **self.rope)
        self.assertGreater(positive["p_gain"], positive["p_loss"])
        self.assertAlmostEqual(positive["p_gain"], negative["p_loss"], places=9)

    def test_rope_matches_independent_mean_integral(self):
        # Integrate variance out instead, giving a different one-dimensional
        # reference: p(mu|D) proportional to N(mu;0,s^2)*(b+SSE(mu)/2)^(-a-n/2).
        values = np.array([.01, .04, .03, -.01])
        a, b, s, delta = 2., .01, .1, .02
        def density(mu):
            return np.exp(-mu*mu/(2*s*s)) * (b + np.square(values-mu).sum()/2)**(-a-len(values)/2)
        norm = integrate.quad(density, -np.inf, np.inf, epsrel=1e-10)[0]
        expected = integrate.quad(density, -delta, delta, epsrel=1e-10)[0]/norm
        actual = rope_probabilities(values, **self.rope)
        self.assertAlmostEqual(actual["p_equivalent"], expected, places=8)

    def test_full_api_pairing_order_and_counts(self):
        options = dict(analyses=["A1", "A2", "A3", "A4", "A5", "A6"],
                       bootstrap_resamples=[100], bootstrap_methods=["percentile"], rope=self.rope)
        result = statistical_analysis(self.metrics, self.baselines, self.cfg, options)
        shuffled = statistical_analysis(self.metrics.sample(frac=1, random_state=3), self.baselines, self.cfg, options)
        for name in result:
            pd.testing.assert_frame_equal(result[name], shuffled[name])
        self.assertEqual(len(result["posthoc_holm"]), 42)
        self.assertTrue(result["posthoc_holm"].family_size.eq(21).all())
        self.assertEqual(len(result["statistical_rope"]), 8)
        self.assertTrue(result["statistical_t"].n.eq(4).all())
        self.assertTrue(result["method_ranks"].mean_rank.between(1, 7).all())

    def test_reject_missing_pairs_duplicates_raw_rows_and_wrong_utility(self):
        options = dict(analyses=["A3"])
        bad_frames = [self.metrics.iloc[1:], pd.concat([self.metrics, self.metrics.iloc[:1]]),
                      self.metrics.assign(t=0), self.metrics.assign(utility=0)]
        changed = self.metrics.copy()
        changed.loc[0, "seed"] = 9999
        bad_frames.append(changed)
        for frame in bad_frames:
            with self.assertRaises(ValueError):
                statistical_analysis(frame, self.baselines, self.cfg, options)

    def test_explicit_rope_prior_required_and_bad_option_rejected(self):
        for options in [{"analyses": ["A5"]}, {"analyses": ["A5"], "rope": {"delta": .02}},
                        {"mystery": True}, {"tie_tolerance": -1}, {"seed": True}]:
            with self.assertRaises(ValueError):
                statistical_analysis(self.metrics, self.baselines, self.cfg, options)
        with self.assertRaises(ValueError):
            rope_probabilities([.1, .2], **dict(self.rope, mu_prior_sd=0))

    def test_friedman_all_ties_and_holm_family(self):
        frame = self.metrics.copy()
        frame["y"], frame["cost"], frame["utility"] = .5, 64., .4375
        result = statistical_analysis(frame, self.baselines, self.cfg, {"analyses": ["A6"]})
        self.assertTrue(result["friedman"].p_value.eq(1).all())
        self.assertTrue(result["method_ranks"].mean_rank.eq(4).all())
        self.assertTrue(result["posthoc_holm"].holm_p_value.eq(1).all())


if __name__ == "__main__":
    unittest.main()
