import numpy as np
import pandas as pd
import pytest
from wealth import market_data, backtest, data


def fake_downloader(tickers, start, end):
    idx = pd.bdate_range("2018-01-01", "2024-12-31")
    rng = np.random.default_rng(0)
    return pd.DataFrame({t: 100 * np.cumprod(1 + rng.normal(0.0003, 0.01, len(idx))) for t in tickers}, index=idx)


def test_fetch_renames_and_caches(tmp_path):
    px = market_data.fetch_prices(cache_dir=str(tmp_path), downloader=fake_downloader)
    assert list(px.columns) == list(market_data.DEFAULT_TICKERS.keys())
    assert (tmp_path / "prices.csv").exists()
    # 2e appel : lit le cache, n'appelle plus le téléchargeur
    def boom(*a, **k): raise AssertionError("ne doit pas retélécharger")
    again = market_data.fetch_prices(cache_dir=str(tmp_path), downloader=boom)
    assert again.shape == px.shape


def test_fetch_raises_on_missing_ticker(tmp_path):
    def partial(tickers, start, end):
        df = fake_downloader(tickers, start, end)
        return df.drop(columns=[tickers[0]])
    with pytest.raises(RuntimeError, match="sans données"):
        market_data.fetch_prices(cache_dir=str(tmp_path), downloader=partial)


def test_fetch_propagates_network_error(tmp_path):
    def down(*a, **k): raise RuntimeError("réseau")
    with pytest.raises(RuntimeError):
        market_data.fetch_prices(cache_dir=str(tmp_path), downloader=down)


def test_monthly_returns_and_min_obs():
    px = fake_downloader(["A", "B"], None, None)
    r = market_data.monthly_returns(px)
    assert r.shape[1] == 2 and len(r) > 60
    with pytest.raises(ValueError, match="trop court"):
        market_data.monthly_returns(px.iloc[:200])


def test_load_csv_french_format(tmp_path):
    p = tmp_path / "pf.csv"
    p.write_text("Date;Actions;Obligations\n31/01/2024;100,0;100,0\n29/02/2024;102,0;100,5\n31/03/2024;101,0;101,0\n", encoding="utf-8")
    r = market_data.load_csv(str(p))
    assert r.shape == (2, 2)
    assert r.iloc[0, 0] == pytest.approx(0.02)


def test_load_csv_rejects_duplicates(tmp_path):
    p = tmp_path / "d.csv"
    p.write_text("Date;A\n31/01/2024;1\n31/01/2024;2\n", encoding="utf-8")
    with pytest.raises(ValueError):
        market_data.load_csv(str(p))


def test_calibrate_matches_known_series():
    idx = pd.date_range("2020-01-31", periods=24, freq="ME")
    r = pd.DataFrame({"A": [0.01] * 24}, index=idx)
    cal = market_data.calibrate(r)
    assert cal["table"].loc["A", "rendement"] == pytest.approx(1.01 ** 12 - 1)
    assert cal["table"].loc["A", "volatilite"] == pytest.approx(0.0)


def test_blend_keeps_priors_for_absent_assets():
    calib = pd.DataFrame({"rendement": [0.10], "volatilite": [0.20]}, index=["Actions Monde"])
    out = market_data.blend_with_priors(calib, data.CMA, 0.5)
    assert out.loc["Private equity"].equals(data.CMA.loc["Private equity"])
    assert out.loc["Actions Monde", "rendement"] == pytest.approx(0.5 * 0.10 + 0.5 * data.CMA.loc["Actions Monde", "rendement"])


def test_backtest_runs_without_private_equity():
    h = data.synthetic_history(n_months=96).drop(columns=["Private equity"])
    t = backtest.run(h)
    assert list(t.index) == ["Prudent", "Équilibré", "Dynamique", "Offensif"]
    assert (t["max_drawdown"] <= 0).all()
    assert "| Prudent |" in backtest.to_markdown(t, ("2019", "2026"), 96, list(h.columns))


def test_worst_year_ignores_incomplete_years():
    idx = pd.date_range("2021-01-31", periods=14, freq="ME")
    r = pd.Series([0.01] * 12 + [-0.5, -0.5], index=idx)   # 2022 : 2 mois seulement, très négatifs
    yr, w = backtest.worst_calendar_year(r)
    assert yr == 2021 and w > 0


# ---------- calibrage appliqué ----------
@pytest.fixture
def clean_assumptions():
    data.reset_assumptions()
    yield
    data.reset_assumptions()


def test_blend_correlations_is_valid_correlation_matrix():
    idx = pd.date_range("2015-01-31", periods=120, freq="ME")
    rng = np.random.default_rng(3)
    r = pd.DataFrame(rng.normal(0.005, 0.03, (120, 4)), index=idx, columns=data.ASSETS[3:7])
    out = market_data.blend_correlations(r.corr(), data.CORR)
    assert np.allclose(np.diag(out.values), 1.0) and np.allclose(out.values, out.values.T)
    assert np.linalg.eigvalsh(out.values).min() > -1e-9
    assert out.loc["Private equity", "Actions Monde"] == pytest.approx(data.CORR.loc["Private equity", "Actions Monde"], abs=0.1)


def test_apply_calibration_changes_planner_assumptions(clean_assumptions):
    from wealth import planner
    w = planner.target_allocation("Dynamique")
    before = planner.portfolio_stats(w)["rendement_espere"]
    new = data.CMA.copy()
    new["rendement"] = new["rendement"] + 0.02
    data.apply_calibration(new)
    assert planner.portfolio_stats(w)["rendement_espere"] == pytest.approx(before + 0.02, abs=1e-9)
    data.reset_assumptions()
    assert planner.portfolio_stats(w)["rendement_espere"] == pytest.approx(before)


def test_save_and_load_calibration_roundtrip(tmp_path, clean_assumptions):
    p = str(tmp_path / "cal.json")
    assert data.load_calibration(p) is False          # pas de fichier : rien n'est appliqué
    t = data._DEFAULT_CMA.copy(); t["volatilite"] = t["volatilite"] * 1.1
    data.save_calibration(t, data._DEFAULT_CORR, p)
    assert data.load_calibration(p) is True
    assert data.CMA.loc["Actions Monde", "volatilite"] == pytest.approx(data._DEFAULT_CMA.loc["Actions Monde", "volatilite"] * 1.1)
