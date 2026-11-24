"""Données de marché réelles : téléchargement (yfinance), cache CSV, import CSV client, calibrage.

Rien n'est simulé ici. Si le réseau ou une source est indisponible, les fonctions lèvent une erreur explicite
plutôt que de produire des chiffres de substitution.
"""
from __future__ import annotations
import os
from typing import Callable
import numpy as np
import pandas as pd

# Un ETF coté représentatif par classe d'actifs (UCITS cotés en euros quand c'est possible).
# Chaque ticker est modifiable : `fetch_prices(tickers=...)`.
DEFAULT_TICKERS = {
    "Liquidités": "XEON.DE",                       # Xtrackers EUR Overnight Rate Swap
    "Obligations souveraines": "EUNH.DE",          # iShares Core Euro Government Bond
    "Obligations Investment Grade": "IEAC.AS",     # iShares Core EUR Corp Bond
    "Actions Monde": "IWDA.AS",                    # iShares Core MSCI World
    "Actions Europe": "EXSA.DE",                   # iShares STOXX Europe 600
    "Immobilier coté": "IPRP.AS",                  # iShares European Property Yield
    "Or": "SGLD.L",                                # Invesco Physical Gold (USD)
}
# NB : "Private equity" n'a pas de série de prix quotidienne représentative et gratuite : il est exclu
# du calibrage historique et garde son hypothèse manuelle (voir data.CMA).

Downloader = Callable[[list, str | None, str | None], pd.DataFrame]


def _yf_download(tickers: list, start: str | None, end: str | None) -> pd.DataFrame:
    import yfinance as yf
    df = yf.download(tickers, start=start, end=end, auto_adjust=True, progress=False, group_by="column")
    if df is None or df.empty:
        raise RuntimeError("Aucune donnée reçue de Yahoo Finance (réseau bloqué ou tickers invalides).")
    px = df["Close"] if isinstance(df.columns, pd.MultiIndex) else df[["Close"]].rename(columns={"Close": tickers[0]})
    return px


def fetch_prices(tickers: dict | None = None, start: str | None = "2012-01-01", end: str | None = None,
                 cache_dir: str = "data", refresh: bool = False, downloader: Downloader | None = None) -> pd.DataFrame:
    """Cours ajustés (dividendes réinvestis) par classe d'actifs, en cache CSV.
    Retourne un DataFrame dont les colonnes sont les noms de classes d'actifs."""
    tickers = tickers or DEFAULT_TICKERS
    os.makedirs(cache_dir, exist_ok=True)
    path = os.path.join(cache_dir, "prices.csv")
    if os.path.exists(path) and not refresh:
        return pd.read_csv(path, index_col=0, parse_dates=True)
    dl = downloader or _yf_download
    px = dl(list(tickers.values()), start, end)
    inv = {v: k for k, v in tickers.items()}
    missing = [t for t in tickers.values() if t not in px.columns or px[t].dropna().empty]
    if missing:
        raise RuntimeError(f"Tickers sans données : {missing}")
    px = px.rename(columns=inv)[list(tickers.keys())].sort_index()
    px.to_csv(path)
    return px


def monthly_returns(prices: pd.DataFrame, min_obs: int = 36) -> pd.DataFrame:
    """Rendements mensuels. Garde uniquement la période commune à toutes les séries ; exige min_obs mois."""
    m = prices.resample("ME").last().dropna(how="all")
    r = m.pct_change().dropna(how="any")
    if len(r) < min_obs:
        raise ValueError(f"Historique commun trop court : {len(r)} mois (minimum {min_obs}).")
    return r


def load_csv(path: str, date_col: str | None = None, kind: str = "prices") -> pd.DataFrame:
    """Import générique CSV (cours ou valorisations d'un portefeuille client).
    Colonnes = lignes du portefeuille, première colonne (ou `date_col`) = dates. kind='prices' ou 'returns'.
    Accepte séparateurs ; ou , et virgule décimale."""
    df = pd.read_csv(path, sep=None, engine="python", decimal=",", thousands=" ")
    date_col = date_col or df.columns[0]
    df[date_col] = pd.to_datetime(df[date_col], dayfirst=True, errors="raise")
    df = df.set_index(date_col).sort_index().apply(pd.to_numeric, errors="raise")
    if df.index.has_duplicates:
        raise ValueError("Dates en double dans le fichier.")
    if kind == "returns":
        return df
    if kind != "prices":
        raise ValueError("kind doit valoir 'prices' ou 'returns'")
    return monthly_returns(df, min_obs=2)


def calibrate(returns: pd.DataFrame, rf_fallback: float = 0.0) -> dict:
    """Rendement annualisé géométrique, volatilité et corrélations estimés sur l'historique commun.
    ATTENTION : le rendement passé est un mauvais estimateur du rendement futur ; il est fourni pour comparaison
    avec les hypothèses de long terme, pas pour remplacer celles-ci."""
    n = len(returns)
    ann_ret = (1 + returns).prod() ** (12 / n) - 1
    vol = returns.std(ddof=1) * np.sqrt(12)
    return {
        "periode": (str(returns.index[0].date()), str(returns.index[-1].date())),
        "n_mois": n,
        "table": pd.DataFrame({"rendement": ann_ret, "volatilite": vol}),
        "correlations": returns.corr(),
    }


def blend_with_priors(calib_table: pd.DataFrame, priors: pd.DataFrame, weight_hist: float = 0.5) -> pd.DataFrame:
    """Hypothèses retenues = moyenne pondérée historique / a priori de long terme (rétrécissement).
    Les classes absentes de l'historique (private equity) conservent l'a priori."""
    out = priors.copy()
    common = [a for a in calib_table.index if a in priors.index]
    out.loc[common, "volatilite"] = weight_hist * calib_table.loc[common, "volatilite"] + (1 - weight_hist) * priors.loc[common, "volatilite"]
    out.loc[common, "rendement"] = weight_hist * calib_table.loc[common, "rendement"] + (1 - weight_hist) * priors.loc[common, "rendement"]
    return out


def _nearest_psd(c: np.ndarray) -> np.ndarray:
    """Rend une matrice de corrélation symétrique semi-définie positive (écrêtage des valeurs propres) à diagonale 1."""
    c = (c + c.T) / 2
    w, v = np.linalg.eigh(c)
    c = v @ np.diag(np.clip(w, 1e-8, None)) @ v.T
    d = np.sqrt(np.diag(c))
    c = c / np.outer(d, d)
    np.fill_diagonal(c, 1.0)
    return c


def blend_correlations(hist_corr: pd.DataFrame, priors: pd.DataFrame, weight_hist: float = 0.5) -> pd.DataFrame:
    """Corrélations retenues : moyenne pondérée historique / a priori sur les classes communes, puis matrice remise
    en forme semi-définie positive. Les classes absentes (private equity) gardent leurs corrélations a priori."""
    out = priors.copy()
    common = [a for a in hist_corr.index if a in priors.index]
    out.loc[common, common] = weight_hist * hist_corr.loc[common, common].values + (1 - weight_hist) * priors.loc[common, common].values
    out.loc[:, :] = _nearest_psd(out.values)
    return out
