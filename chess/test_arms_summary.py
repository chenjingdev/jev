from arms_summary import clip, sign_test, two_proportion_z


def test_clip_bounds_mate_scores():
    assert clip(10000) == 1000 and clip(-9995) == -1000 and clip(-4) == -4


def test_sign_test_matches_binomial():
    assert sign_test(0, 0) == 1.0
    assert abs(sign_test(5, 5) - 1.0) < 1e-9
    assert abs(sign_test(10, 0) - 2 / 1024) < 1e-12


def test_two_proportion_z_is_zero_for_equal_rates():
    z, p = two_proportion_z(0.5, 100, 0.5, 100)
    assert z == 0.0 and p == 1.0
    z, p = two_proportion_z(0.6, 500, 0.4, 500)
    assert z > 6 and p < 1e-6


def test_game_level_bootstrap_uses_game_means():
    from arms_summary import per_game_means, bootstrap_diff
    rows = [{'game': 1, 'grade': {'pick_minus_base': 100}}, {'game': 1, 'grade': {'pick_minus_base': -100}},
            {'game': 2, 'grade': {'pick_minus_base': 50}}, {'game': 2, 'grade': {'pick_minus_base': 9999}}]
    means = per_game_means(rows)
    assert means == {1: 0, 2: 525}
    lo, hi = bootstrap_diff([10, 10, 10], [0, 0, 0], n=200)
    assert lo == 10 and hi == 10
