"""Hypothèses de marché et génération de données synthétiques.

Les rendements, volatilités et corrélations ci-dessous sont des hypothèses ILLUSTRATIVES de long terme,
ordres de grandeur proches des consensus publics. Elles ne sont ni une prévision ni une recommandation.
"""
from __future__ import annotations
import numpy as np
import pandas as pd

ASSETS = ["Liquidités", "Obligations souveraines", "Obligations Investment Grade",
          "Actions Monde", "Actions Europe", "Immobilier coté", "Or", "Private equity"]

# rendement annuel espéré (nominal), volatilité annuelle
CMA = pd.DataFrame({
    "rendement": [0.025, 0.030, 0.040, 0.070, 0.070, 0.060, 0.035, 0.095],
    "volatilite": [0.005, 0.060, 0.065, 0.155, 0.170, 0.160, 0.150, 0.220],
}, index=ASSETS)

_CORR = np.array([
    [1.00, 0.10, 0.10, 0.00, 0.00, 0.00, 0.05, 0.00],
    [0.10, 1.00, 0.80, -0.10, -0.05, 0.10, 0.20, -0.05],
    [0.10, 0.80, 1.00, 0.30, 0.35, 0.40, 0.15, 0.25],
    [0.00, -0.10, 0.30, 1.00, 0.90, 0.75, 0.10, 0.80],
    [0.00, -0.05, 0.35, 0.90, 1.00, 0.75, 0.10, 0.75],
    [0.00, 0.10, 0.40, 0.75, 0.75, 1.00, 0.10, 0.65],
    [0.05, 0.20, 0.15, 0.10, 0.10, 0.10, 1.00, 0.05],
    [0.00, -0.05, 0.25, 0.80, 0.75, 0.65, 0.05, 1.00],
])
CORR = pd.DataFrame(_CORR, index=ASSETS, columns=ASSETS)


def cov_matrix(assets=None) -> pd.DataFrame:
    assets = list(assets or ASSETS)
    vol = CMA.loc[assets, "volatilite"].values
    c = CORR.loc[assets, assets].values
    return pd.DataFrame(np.outer(vol, vol) * c, index=assets, columns=assets)


def simulate_annual_returns(weights: pd.Series, n_paths: int, n_years: int, seed: int = 42) -> np.ndarray:
    """Rendements annuels du portefeuille (log-normaux multivariés), shape (n_paths, n_years).
    Rééquilibrage annuel vers les poids cibles."""
    w = weights.astype(float)
    w = w / w.sum()
    assets = list(w.index)
    mu = CMA.loc[assets, "rendement"].values
    cov = cov_matrix(assets).values
    rng = np.random.default_rng(seed)
    # log-rendements : mu_log = ln(1+mu) - 0.5*var pour que E[1+r] = 1+mu
    mu_log = np.log1p(mu) - 0.5 * np.diag(cov)
    z = rng.multivariate_normal(mu_log, cov, size=(n_paths, n_years))
    asset_ret = np.expm1(z)
    return asset_ret @ w.values


def synthetic_history(weights: dict | None = None, n_months: int = 60, seed: int = 7, start="2019-12-31") -> pd.DataFrame:
    """Historique mensuel synthétique (rendements) pour démontrer l'analyse de portefeuille.
    DONNÉES SIMULÉES, pas des cours réels."""
    assets = ASSETS
    mu = CMA["rendement"].values
    cov = cov_matrix(assets).values / 12
    rng = np.random.default_rng(seed)
    r = rng.multivariate_normal(np.log1p(mu) / 12 - 0.5 * np.diag(cov), cov, size=n_months)
    idx = pd.date_range(start, periods=n_months, freq="ME")
    return pd.DataFrame(np.expm1(r), index=idx, columns=assets)


# ---------------------------------------------------------------------------------------------
# Calibrage : remplace en place les hypothèses par défaut (rendements, volatilités, corrélations)
# ---------------------------------------------------------------------------------------------
import json as _json
import os as _os

_DEFAULT_CMA = CMA.copy()
_DEFAULT_CORR = CORR.copy()


def reset_assumptions() -> None:
    """Revient aux hypothèses de long terme d'origine."""
    CMA.loc[:, :] = _DEFAULT_CMA.values
    CORR.loc[:, :] = _DEFAULT_CORR.values


def apply_calibration(table: pd.DataFrame, corr: pd.DataFrame | None = None) -> None:
    """Applique des hypothèses calibrées. `table` : colonnes rendement et volatilite, index = classes d'actifs."""
    for a in table.index:
        if a in CMA.index:
            CMA.loc[a, "rendement"] = float(table.loc[a, "rendement"])
            CMA.loc[a, "volatilite"] = float(table.loc[a, "volatilite"])
    if corr is not None:
        common = [a for a in corr.index if a in CORR.index]
        CORR.loc[common, common] = corr.loc[common, common].values


def save_calibration(table: pd.DataFrame, corr: pd.DataFrame, path: str) -> None:
    _os.makedirs(_os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        _json.dump({"table": table.to_dict(), "corr": corr.to_dict()}, f, ensure_ascii=False, indent=1)


def load_calibration(path: str = "data/calibration.json") -> bool:
    """Charge et applique le calibrage s'il existe. Retourne True si appliqué."""
    if not _os.path.exists(path):
        return False
    with open(path, encoding="utf-8") as f:
        j = _json.load(f)
    apply_calibration(pd.DataFrame(j["table"]), pd.DataFrame(j["corr"]))
    return True
