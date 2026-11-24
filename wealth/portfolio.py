"""Analyse d'un portefeuille privé : performance, risque, allocation, dérive et rééquilibrage."""
from __future__ import annotations
import numpy as np
import pandas as pd

PERIODS = 12  # données mensuelles


def portfolio_returns(returns: pd.DataFrame, weights: pd.Series) -> pd.Series:
    """Rendements du portefeuille, rééquilibré à chaque période vers `weights`."""
    w = weights.reindex(returns.columns).fillna(0.0)
    if abs(w.sum() - 1) > 1e-6:
        raise ValueError("les poids doivent sommer à 1")
    return (returns * w).sum(axis=1)


def cumulative(r: pd.Series) -> pd.Series:
    return (1 + r).cumprod()


def annualized_return(r: pd.Series) -> float:
    n = len(r)
    return float((1 + r).prod() ** (PERIODS / n) - 1)


def annualized_vol(r: pd.Series) -> float:
    return float(r.std(ddof=1) * np.sqrt(PERIODS))


def sharpe(r: pd.Series, rf: float = 0.02) -> float:
    vol = annualized_vol(r)
    return float((annualized_return(r) - rf) / vol) if vol else float("nan")


def max_drawdown(r: pd.Series) -> float:
    c = cumulative(r)
    return float((c / c.cummax() - 1).min())


def var_cvar(r: pd.Series, level: float = 0.95) -> tuple[float, float]:
    """VaR et CVaR historiques mensuels (valeurs négatives = pertes)."""
    var = float(np.percentile(r, (1 - level) * 100))
    cvar = float(r[r <= var].mean())
    return var, cvar


def beta_tracking(r: pd.Series, bench: pd.Series) -> dict:
    df = pd.concat([r, bench], axis=1, keys=["p", "b"]).dropna()
    cov = np.cov(df["p"], df["b"], ddof=1)
    beta = cov[0, 1] / cov[1, 1]
    active = df["p"] - df["b"]
    te = active.std(ddof=1) * np.sqrt(PERIODS)
    ir = (annualized_return(df["p"]) - annualized_return(df["b"])) / te if te else float("nan")
    return {"beta": float(beta), "tracking_error": float(te), "information_ratio": float(ir)}


def risk_contribution(returns: pd.DataFrame, weights: pd.Series) -> pd.Series:
    """Contribution de chaque ligne à la volatilité totale (somme = 100 %)."""
    w = weights.reindex(returns.columns).fillna(0.0).values
    cov = returns.cov().values
    port_var = w @ cov @ w
    contrib = w * (cov @ w) / port_var
    return pd.Series(contrib, index=returns.columns)


def drift(current: pd.Series, target: pd.Series) -> pd.DataFrame:
    idx = current.index.union(target.index)
    df = pd.DataFrame({"actuel": current.reindex(idx).fillna(0.0), "cible": target.reindex(idx).fillna(0.0)})
    df["ecart"] = df["actuel"] - df["cible"]
    return df


def rebalancing_trades(values: pd.Series, target: pd.Series, band: float = 0.03) -> pd.DataFrame:
    """Ordres pour revenir à la cible. Ne rééquilibre que si une ligne dépasse la bande de tolérance (en points d'allocation)."""
    total = values.sum()
    cur = values / total
    d = drift(cur, target)
    trigger = bool((d["ecart"].abs() > band).any())
    out = d.copy()
    out["montant_a_trader"] = np.where(trigger, (out["cible"] - out["actuel"]) * total, 0.0)
    out.attrs["rebalance"] = trigger
    return out


def summary(r: pd.Series, bench: pd.Series | None = None, rf: float = 0.02) -> dict:
    var, cvar = var_cvar(r)
    s = {
        "rendement_annualise": annualized_return(r),
        "volatilite": annualized_vol(r),
        "sharpe": sharpe(r, rf),
        "max_drawdown": max_drawdown(r),
        "VaR_95_mensuelle": var,
        "CVaR_95_mensuelle": cvar,
    }
    if bench is not None:
        s.update(beta_tracking(r, bench))
    return s
