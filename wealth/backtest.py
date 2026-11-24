"""Backtest des profils de risque sur historique réel (ou tout DataFrame de rendements mensuels)."""
from __future__ import annotations
import pandas as pd
from . import planner, portfolio


def _profile_weights(profile: str, available: list) -> pd.Series:
    """Poids du profil restreints aux classes disponibles, renormalisés (ex. sans private equity)."""
    w = planner.target_allocation(profile)
    w = w[w.index.isin(available)]
    return w / w.sum()


def worst_calendar_year(r: pd.Series) -> tuple[int, float]:
    y = (1 + r).groupby(r.index.year).prod() - 1
    # ignore les années incomplètes (< 12 mois)
    full = r.groupby(r.index.year).count()
    y = y[full[full >= 12].index]
    if y.empty:
        return (int(r.index[0].year), float("nan"))
    return int(y.idxmin()), float(y.min())


def run(returns: pd.DataFrame, rf: float = 0.02, rebalance: str = "monthly") -> pd.DataFrame:
    """Une ligne par profil : rendement annualisé, volatilité, Sharpe, drawdown max, pire année civile complète."""
    rows = {}
    for p in planner.PROFILES:
        w = _profile_weights(p, list(returns.columns))
        r = portfolio.portfolio_returns(returns[w.index], w)
        yr, worst = worst_calendar_year(r)
        s = portfolio.summary(r, rf=rf)
        rows[p] = {"rendement_annualise": s["rendement_annualise"], "volatilite": s["volatilite"], "sharpe": s["sharpe"],
                   "max_drawdown": s["max_drawdown"], "pire_annee": worst, "annee_pire": yr}
    return pd.DataFrame(rows).T


def to_markdown(table: pd.DataFrame, period: tuple[str, str], n_months: int, assets: list) -> str:
    lines = [f"Backtest des 4 profils sur **{period[0]} → {period[1]}** ({n_months} mois), rééquilibrage mensuel, "
             f"sans frais ni fiscalité. Classes utilisées : {', '.join(assets)}.", "",
             "| Profil | Rendement annualisé | Volatilité | Sharpe | Drawdown max | Pire année |", "|---|---|---|---|---|---|"]
    for p, r in table.iterrows():
        lines.append(f"| {p} | {r['rendement_annualise']*100:.1f} % | {r['volatilite']*100:.1f} % | {r['sharpe']:.2f} | "
                     f"{r['max_drawdown']*100:.1f} % | {r['pire_annee']*100:.1f} % ({int(r['annee_pire'])}) |")
    lines += ["", "Les performances passées ne préjugent pas des performances futures."]
    return "\n".join(lines)
