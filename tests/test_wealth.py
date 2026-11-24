import math
import numpy as np
import pandas as pd
import pytest
from wealth import planner, portfolio, structured, data


# ---------- planner ----------
def test_allocations_sum_to_one():
    for p in planner.PROFILES:
        assert planner.target_allocation(p).sum() == pytest.approx(1.0)


def test_risk_profile_capped_by_loss_tolerance():
    assert planner.risk_profile(30, 1, 4, 4) == "Prudent"
    assert planner.risk_profile(30, 4, 4, 4) == "Offensif"


def test_risk_profile_validates_inputs():
    with pytest.raises(ValueError):
        planner.risk_profile(10, 5, 2, 2)
    with pytest.raises(ValueError):
        planner.risk_profile(0, 2, 2, 2)


def test_riskier_profile_has_higher_vol_and_return():
    s = [planner.portfolio_stats(planner.target_allocation(p)) for p in planner.PROFILES]
    assert all(s[i]["volatilite"] < s[i + 1]["volatilite"] for i in range(3))
    assert all(s[i]["rendement_espere"] < s[i + 1]["rendement_espere"] for i in range(3))


def test_projection_mean_matches_expected_return():
    w = planner.target_allocation("Équilibré")
    sc = planner.Scenario(100_000, 0.0, inflation=0.0, frais_annuels=0.0)
    paths = planner.project(w, sc, 10, n_paths=40_000)
    exp = 100_000 * (1 + planner.portfolio_stats(w)["rendement_espere"]) ** 10
    assert paths[:, -1].mean() == pytest.approx(exp, rel=0.02)


def test_projection_deterministic_with_seed():
    w = planner.target_allocation("Prudent")
    sc = planner.Scenario(100_000, 5000)
    assert np.array_equal(planner.project(w, sc, 5, 100, seed=1), planner.project(w, sc, 5, 100, seed=1))


def test_wealth_never_negative_and_withdrawals():
    w = planner.target_allocation("Prudent")
    sc = planner.Scenario(100_000, 0, retrait_annuel=80_000, debut_retraits=0)
    assert planner.project(w, sc, 10, 500).min() >= 0


def test_more_contribution_raises_probability():
    w = planner.target_allocation("Dynamique")
    g = planner.Goal("x", 800_000, 15)
    lo = planner.goal_probability(planner.project(w, planner.Scenario(200_000, 5_000), 15, 5000), g)
    hi = planner.goal_probability(planner.project(w, planner.Scenario(200_000, 30_000), 15, 5000), g)
    assert hi > lo


def test_required_contribution_reaches_confidence():
    w = planner.target_allocation("Équilibré")
    sc = planner.Scenario(300_000)
    g = planner.Goal("x", 700_000, 12)
    c = planner.required_contribution(w, sc, g, 0.7, n_paths=3000)
    sc2 = planner.Scenario(300_000, c)
    assert planner.goal_probability(planner.project(w, sc2, 12, 3000), g) >= 0.69


# ---------- portfolio ----------
@pytest.fixture
def hist():
    return data.synthetic_history(n_months=60, seed=3)


def test_constant_returns_metrics():
    r = pd.Series([0.01] * 24)
    assert portfolio.annualized_return(r) == pytest.approx(1.01 ** 12 - 1)
    assert portfolio.annualized_vol(r) == pytest.approx(0.0)
    assert portfolio.max_drawdown(r) == pytest.approx(0.0)


def test_max_drawdown_known_case():
    r = pd.Series([0.10, -0.20, 0.05])
    assert portfolio.max_drawdown(r) == pytest.approx(-0.20)


def test_var_cvar_ordering(hist):
    r = portfolio.portfolio_returns(hist, planner.target_allocation("Dynamique"))
    var, cvar = portfolio.var_cvar(r)
    assert cvar <= var < 0.05


def test_weights_must_sum_to_one(hist):
    with pytest.raises(ValueError):
        portfolio.portfolio_returns(hist, pd.Series({"Actions Monde": 0.5}))


def test_beta_of_portfolio_vs_itself_is_one(hist):
    r = portfolio.portfolio_returns(hist, planner.target_allocation("Équilibré"))
    b = portfolio.beta_tracking(r, r)
    assert b["beta"] == pytest.approx(1.0) and b["tracking_error"] == pytest.approx(0.0, abs=1e-12)


def test_risk_contributions_sum_to_one(hist):
    w = planner.target_allocation("Équilibré")
    assert portfolio.risk_contribution(hist, w).sum() == pytest.approx(1.0)


def test_rebalancing_respects_band():
    target = pd.Series({"A": 0.5, "B": 0.5})
    inside = portfolio.rebalancing_trades(pd.Series({"A": 51.0, "B": 49.0}), target, band=0.03)
    assert not inside.attrs["rebalance"] and inside["montant_a_trader"].abs().sum() == 0
    outside = portfolio.rebalancing_trades(pd.Series({"A": 60.0, "B": 40.0}), target, band=0.03)
    assert outside.attrs["rebalance"]
    assert outside["montant_a_trader"].sum() == pytest.approx(0.0)
    assert outside.loc["A", "montant_a_trader"] == pytest.approx(-10.0)


# ---------- structured ----------
def test_put_call_parity():
    S, K, T, r, q, s = 100, 105, 2, 0.03, 0.01, 0.2
    lhs = structured.bs_call(S, K, T, r, q, s) - structured.bs_put(S, K, T, r, q, s)
    assert lhs == pytest.approx(S * math.exp(-q * T) - K * math.exp(-r * T))


def test_bs_known_value():
    assert structured.bs_call(100, 100, 1, 0.05, 0.0, 0.2) == pytest.approx(10.4506, abs=1e-3)


def test_gbm_martingale():
    p = structured.simulate_gbm(100, 0.03, 0.01, 0.2, 5, 5, 100_000, seed=2)
    assert p[:, -1].mean() == pytest.approx(100 * math.exp(0.02 * 5), rel=0.01)


def test_autocall_zero_vol_called_immediately():
    # volatilité nulle, drift positif : rappel dès la 1re observation
    a = structured.Autocall(maturite=5, coupon_annuel=0.06)
    res = structured.price_autocall(a, r=0.05, q=0.0, sigma=1e-9, n_paths=1000)
    assert res["proba_rappel_cumulee"][1] == pytest.approx(1.0)
    assert res["prix_pct_nominal"] == pytest.approx((1.06) * math.exp(-0.05) * 100, rel=1e-3)
    assert res["proba_perte_capital"] == 0.0


def test_autocall_price_increases_with_coupon():
    lo = structured.price_autocall(structured.Autocall(coupon_annuel=0.03), n_paths=20_000)["prix_pct_nominal"]
    hi = structured.price_autocall(structured.Autocall(coupon_annuel=0.08), n_paths=20_000)["prix_pct_nominal"]
    assert hi > lo


def test_autocall_lower_capital_barrier_reduces_loss_probability():
    a = structured.price_autocall(structured.Autocall(barriere_capital=0.6), n_paths=20_000)["proba_perte_capital"]
    b = structured.price_autocall(structured.Autocall(barriere_capital=0.5), n_paths=20_000)["proba_perte_capital"]
    assert b < a


def test_fair_coupon_hits_target_price():
    a = structured.Autocall()
    c = structured.fair_coupon(a, 98.0, n_paths=10_000)
    p = structured.price_autocall(structured.Autocall(coupon_annuel=c), n_paths=10_000)["prix_pct_nominal"]
    assert p == pytest.approx(98.0, abs=0.05)


def test_capital_protected_budget_identity():
    res = structured.price_capital_protege(structured.CapitalProtege(), r=0.03, q=0.0, sigma=0.2)
    assert res["valeur_zero_coupon_pct"] + res["budget_option_pct"] == pytest.approx(100.0)
    assert res["participation_pct"] == pytest.approx(res["budget_option_pct"] / res["prix_call_atm_pct"] * 100)


def test_capital_protected_payoff_floor():
    p = structured.CapitalProtege()
    pay = structured.payoff_capital_protege(np.array([0.3, 1.0, 1.5]), p, 1.0)
    assert pay.tolist() == [1.0, 1.0, 1.5]


# ---------- reverse convertible / phoenix ----------
def test_rc_zero_vol_pays_nominal_plus_coupon():
    rc = structured.ReverseConvertible(maturite=1, coupon_annuel=0.08)
    res = structured.price_reverse_convertible(rc, r=0.03, q=0.0, sigma=1e-9, n_paths=1000)
    assert res["prix_pct_nominal"] == pytest.approx(1.08 * math.exp(-0.03) * 100, rel=1e-3)
    assert res["proba_perte_capital"] == 0.0 and res["proba_knock_in"] == 0.0


def test_rc_lower_barrier_lowers_knock_in():
    hi = structured.price_reverse_convertible(structured.ReverseConvertible(barriere=0.8), n_paths=20_000)["proba_knock_in"]
    lo = structured.price_reverse_convertible(structured.ReverseConvertible(barriere=0.6), n_paths=20_000)["proba_knock_in"]
    assert lo < hi


def test_rc_price_increases_with_coupon_and_decreases_with_vol_risk():
    a = structured.price_reverse_convertible(structured.ReverseConvertible(coupon_annuel=0.04), n_paths=20_000)["prix_pct_nominal"]
    b = structured.price_reverse_convertible(structured.ReverseConvertible(coupon_annuel=0.10), n_paths=20_000)["prix_pct_nominal"]
    assert b > a
    v1 = structured.price_reverse_convertible(structured.ReverseConvertible(), sigma=0.15, n_paths=20_000)["prix_pct_nominal"]
    v2 = structured.price_reverse_convertible(structured.ReverseConvertible(), sigma=0.35, n_paths=20_000)["prix_pct_nominal"]
    assert v2 < v1     # l'investisseur vend un put : plus de vol = valeur plus basse pour lui


def test_rc_loss_probability_bounded_by_knock_in():
    res = structured.price_reverse_convertible(structured.ReverseConvertible(), n_paths=20_000)
    assert res["proba_perte_capital"] <= res["proba_knock_in"]


def test_fair_rc_coupon_hits_target():
    rc = structured.ReverseConvertible()
    c = structured.fair_rc_coupon(rc, 98.0, n_paths=10_000)
    p = structured.price_reverse_convertible(structured.ReverseConvertible(coupon_annuel=c), n_paths=10_000)["prix_pct_nominal"]
    assert p == pytest.approx(98.0, abs=0.05)


def test_rc_comparison_probabilities_valid():
    c = structured.compare_rc_with_underlying(structured.ReverseConvertible(), n_paths=10_000)
    assert 0 <= c["proba_produit_bat_indice"] <= 1 and c["pire_5pct_produit"] > c["pire_5pct_indice"]


def test_phoenix_memory_adds_value():
    a = structured.price_autocall(structured.Phoenix(memoire=True), n_paths=20_000)["prix_pct_nominal"]
    b = structured.price_autocall(structured.Phoenix(memoire=False), n_paths=20_000)["prix_pct_nominal"]
    assert a >= b


def test_phoenix_coupon_barrier_distinct_from_capital_barrier():
    ph = structured.Phoenix()
    assert ph.barriere_coupon > ph.barriere_capital and isinstance(ph, structured.Autocall)
    # un coupon plus facile à toucher vaut plus cher
    easy = structured.price_autocall(structured.Phoenix(barriere_coupon=0.6), n_paths=20_000)["prix_pct_nominal"]
    hard = structured.price_autocall(structured.Phoenix(barriere_coupon=0.9), n_paths=20_000)["prix_pct_nominal"]
    assert easy > hard
