"""Planification patrimoniale : profil de risque, allocation cible, projection Monte Carlo."""
from __future__ import annotations
from dataclasses import dataclass
import numpy as np
import pandas as pd
from .data import ASSETS, CMA, cov_matrix, simulate_annual_returns

PROFILES = ["Prudent", "Équilibré", "Dynamique", "Offensif"]

# Allocations cibles par profil (somme = 1)
ALLOCATIONS = pd.DataFrame({
    "Prudent":   [0.10, 0.30, 0.35, 0.10, 0.05, 0.05, 0.05, 0.00],
    "Équilibré": [0.05, 0.15, 0.25, 0.20, 0.15, 0.07, 0.05, 0.08],
    "Dynamique": [0.03, 0.07, 0.15, 0.28, 0.20, 0.08, 0.04, 0.15],
    "Offensif":  [0.02, 0.03, 0.05, 0.33, 0.22, 0.08, 0.02, 0.25],
}, index=ASSETS)


def risk_profile(horizon_years: int, loss_tolerance: int, experience: int, income_stability: int) -> str:
    """Score simple de 4 critères.
    horizon_years : durée d'investissement ; loss_tolerance, experience, income_stability : de 1 (faible) à 4 (élevé).
    Le profil est plafonné par la tolérance aux pertes (règle de prudence)."""
    for name, v in [("loss_tolerance", loss_tolerance), ("experience", experience), ("income_stability", income_stability)]:
        if v not in (1, 2, 3, 4):
            raise ValueError(f"{name} doit valoir 1 à 4")
    if horizon_years <= 0:
        raise ValueError("horizon_years doit être positif")
    h = 1 if horizon_years < 3 else 2 if horizon_years < 7 else 3 if horizon_years < 15 else 4
    score = (h + loss_tolerance + experience + income_stability) / 4
    idx = min(3, max(0, int(round(score)) - 1))
    idx = min(idx, loss_tolerance - 1)
    return PROFILES[idx]


def target_allocation(profile: str) -> pd.Series:
    if profile not in PROFILES:
        raise ValueError(f"profil inconnu : {profile}")
    return ALLOCATIONS[profile].copy()


def portfolio_stats(weights: pd.Series) -> dict:
    w = weights.values
    mu = CMA.loc[weights.index, "rendement"].values
    cov = cov_matrix(list(weights.index)).values
    vol = float(np.sqrt(w @ cov @ w))
    ret = float(w @ mu)
    return {"rendement_espere": ret, "volatilite": vol, "ratio_rendement_risque": ret / vol if vol else float("nan")}


@dataclass
class Goal:
    nom: str
    montant_cible: float          # en euros d'aujourd'hui
    horizon_annees: int


@dataclass
class Scenario:
    patrimoine_initial: float
    versement_annuel: float = 0.0
    retrait_annuel: float = 0.0     # retraits à partir de l'année `debut_retraits`
    debut_retraits: int = 10_000    # par défaut jamais
    inflation: float = 0.02
    frais_annuels: float = 0.01     # frais totaux (gestion + produits)
    versements_indexes: bool = True


def project(weights: pd.Series, scenario: Scenario, n_years: int, n_paths: int = 10_000, seed: int = 42) -> np.ndarray:
    """Trajectoires de patrimoine NOMINAL, shape (n_paths, n_years+1). Colonne 0 = patrimoine initial."""
    r = simulate_annual_returns(weights, n_paths, n_years, seed)
    wealth = np.empty((n_paths, n_years + 1))
    wealth[:, 0] = scenario.patrimoine_initial
    for t in range(1, n_years + 1):
        idx = (1 + scenario.inflation) ** (t - 1) if scenario.versements_indexes else 1.0
        flow = scenario.versement_annuel * idx
        if t > scenario.debut_retraits:
            flow -= scenario.retrait_annuel * (1 + scenario.inflation) ** (t - 1)
        w = wealth[:, t - 1] * (1 + r[:, t - 1] - scenario.frais_annuels) + flow
        wealth[:, t] = np.maximum(w, 0.0)     # pas de patrimoine négatif
    return wealth


def goal_probability(wealth_paths: np.ndarray, goal: Goal, inflation: float = 0.02) -> float:
    """Probabilité d'atteindre l'objectif (exprimé en euros d'aujourd'hui) à l'horizon."""
    if goal.horizon_annees >= wealth_paths.shape[1]:
        raise ValueError("horizon de l'objectif au-delà de la projection")
    target_nominal = goal.montant_cible * (1 + inflation) ** goal.horizon_annees
    return float((wealth_paths[:, goal.horizon_annees] >= target_nominal).mean())


def summarize(wealth_paths: np.ndarray, inflation: float = 0.02) -> pd.DataFrame:
    """Percentiles du patrimoine réel (euros d'aujourd'hui) par année."""
    n_years = wealth_paths.shape[1] - 1
    deflator = (1 + inflation) ** np.arange(n_years + 1)
    real = wealth_paths / deflator
    q = np.percentile(real, [5, 25, 50, 75, 95], axis=0)
    return pd.DataFrame(q.T, columns=["P5", "P25", "P50", "P75", "P95"])


def required_contribution(weights, scenario: Scenario, goal: Goal, confiance: float = 0.7,
                          n_paths: int = 5000, seed: int = 42) -> float:
    """Versement annuel minimal pour atteindre l'objectif avec la probabilité `confiance` (recherche dichotomique)."""
    lo, hi = 0.0, max(goal.montant_cible, 1.0)
    for _ in range(30):
        mid = (lo + hi) / 2
        sc = Scenario(**{**scenario.__dict__, "versement_annuel": mid})
        p = goal_probability(project(weights, sc, goal.horizon_annees, n_paths, seed), goal, scenario.inflation)
        if p >= confiance:
            hi = mid
        else:
            lo = mid
    return hi
