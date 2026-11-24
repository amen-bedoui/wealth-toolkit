"""Produits structurés : autocall (Phoenix simplifié) et note à capital protégé. Valorisation Monte Carlo / Black-Scholes."""
from __future__ import annotations
from dataclasses import dataclass
import numpy as np
from math import erf, exp, log, sqrt


def _N(x: float) -> float:
    return 0.5 * (1 + erf(x / sqrt(2)))


def bs_call(S: float, K: float, T: float, r: float, q: float, sigma: float) -> float:
    if T <= 0:
        return max(S - K, 0.0)
    if sigma <= 0:
        return max(S * exp(-q * T) - K * exp(-r * T), 0.0)
    d1 = (log(S / K) + (r - q + 0.5 * sigma ** 2) * T) / (sigma * sqrt(T))
    d2 = d1 - sigma * sqrt(T)
    return S * exp(-q * T) * _N(d1) - K * exp(-r * T) * _N(d2)


def bs_put(S: float, K: float, T: float, r: float, q: float, sigma: float) -> float:
    return bs_call(S, K, T, r, q, sigma) - S * exp(-q * T) + K * exp(-r * T)


def simulate_gbm(S0: float, r: float, q: float, sigma: float, T: float, n_steps: int, n_paths: int, seed: int = 1) -> np.ndarray:
    """Trajectoires risque-neutre, shape (n_paths, n_steps). Pas de temps T/n_steps, sans le point initial."""
    rng = np.random.default_rng(seed)
    dt = T / n_steps
    if n_paths % 2 == 0:                                   # variables antithétiques (réduction de variance)
        half = rng.standard_normal((n_paths // 2, n_steps))
        z = np.concatenate([half, -half])
    else:
        z = rng.standard_normal((n_paths, n_steps))
    inc = (r - q - 0.5 * sigma ** 2) * dt + sigma * sqrt(dt) * z
    return S0 * np.exp(np.cumsum(inc, axis=1))


@dataclass
class Autocall:
    """Autocall avec coupons conditionnels (mémoire optionnelle).
    Observations annuelles (n_obs par an configurable). Niveaux exprimés en % du niveau initial."""
    maturite: int = 8                 # années
    obs_par_an: int = 1
    barriere_rappel: float = 1.00     # rappel si indice >= barrière
    barriere_coupon: float = 0.70     # coupon versé si indice >= barrière
    barriere_capital: float = 0.60    # perte en capital à l'échéance si indice < barrière
    coupon_annuel: float = 0.07
    memoire: bool = True
    nominal: float = 100.0
    premiere_obs_rappel: int = 1      # numéro de la 1re observation avec rappel possible


def price_autocall(p: Autocall, S0: float = 100.0, r: float = 0.025, q: float = 0.03, sigma: float = 0.18,
                   n_paths: int = 50_000, seed: int = 1) -> dict:
    """Prix (en % du nominal), probabilité de rappel par date, perte en capital, durée de vie moyenne."""
    n_obs = p.maturite * p.obs_par_an
    paths = simulate_gbm(S0, r, q, sigma, p.maturite, n_obs, n_paths, seed) / S0
    dt = 1 / p.obs_par_an
    cpn = p.coupon_annuel * dt
    n = paths.shape[0]
    alive = np.ones(n, dtype=bool)
    pv = np.zeros(n)
    owed = np.zeros(n)       # coupons mémorisés
    called_at = np.full(n, np.nan)
    for i in range(n_obs):
        t = (i + 1) * dt
        disc = exp(-r * t)
        s = paths[:, i]
        pay_cpn = alive & (s >= p.barriere_coupon)
        amount = np.where(pay_cpn, cpn + (owed if p.memoire else 0.0), 0.0)
        owed = np.where(alive & ~pay_cpn, owed + cpn, np.where(pay_cpn, 0.0, owed))
        pv += amount * disc * p.nominal
        if i + 1 >= p.premiere_obs_rappel:
            call = alive & (s >= p.barriere_rappel)
            pv += np.where(call, p.nominal * disc, 0.0)
            called_at[call] = t
            alive = alive & ~call
    # échéance
    sT = paths[:, -1]
    disc_T = exp(-r * p.maturite)
    redemption = np.where(sT >= p.barriere_capital, 1.0, sT)
    pv += np.where(alive, redemption * p.nominal * disc_T, 0.0)
    loss = alive & (sT < p.barriere_capital)
    times = np.where(np.isnan(called_at), p.maturite, called_at)
    call_by_year = {int(y): float(np.nanmean(np.where(np.isnan(called_at), 0, called_at <= y))) for y in range(1, p.maturite + 1)}
    return {
        "prix_pct_nominal": float(pv.mean() / p.nominal * 100),
        "erreur_standard_pct": float(pv.std(ddof=1) / sqrt(n) / p.nominal * 100),
        "proba_rappel_cumulee": call_by_year,
        "proba_perte_capital": float(loss.mean()),
        "perte_moyenne_si_perte_pct": float((1 - sT[loss]).mean() * 100) if loss.any() else 0.0,
        "duree_vie_moyenne_annees": float(times.mean()),
    }


@dataclass
class CapitalProtege:
    maturite: int = 6
    protection: float = 1.00          # % du nominal garanti à l'échéance
    nominal: float = 100.0


def price_capital_protege(p: CapitalProtege, S0=100.0, r=0.03, q=0.03, sigma=0.18, taux_emetteur_spread=0.0) -> dict:
    """Décompose la note : obligation zéro-coupon + call. Calcule la participation que permet le budget d'options.
    La participation = budget optionnel / prix du call ATM. `taux_emetteur_spread` = spread de crédit de l'émetteur."""
    zc = p.protection * exp(-(r + taux_emetteur_spread) * p.maturite)
    budget = 1.0 - zc
    call = bs_call(S0, S0, p.maturite, r, q, sigma) / S0
    participation = budget / call if call > 0 else float("nan")
    return {
        "valeur_zero_coupon_pct": zc * 100,
        "budget_option_pct": budget * 100,
        "prix_call_atm_pct": call * 100,
        "participation_pct": participation * 100,
    }


def payoff_capital_protege(S_T_over_S0: np.ndarray, p: CapitalProtege, participation: float) -> np.ndarray:
    return p.protection + participation * np.maximum(S_T_over_S0 - 1.0, 0.0)


def compare_with_underlying(p: Autocall, S0=100.0, r=0.025, q=0.03, sigma=0.18, mu=0.07, n_paths=20_000, seed=3) -> dict:
    """Comparaison PROBABILISTE (monde réel, drift mu) du produit avec l'indice détenu en direct (dividendes réinvestis).
    Retourne le TRI annualisé moyen et médian de chaque stratégie, et la probabilité que le produit batte l'indice."""
    n_obs = p.maturite * p.obs_par_an
    dt = 1 / p.obs_par_an
    price_paths = simulate_gbm(S0, mu, q, sigma, p.maturite, n_obs, n_paths, seed) / S0       # indice prix : drift mu - q
    paths = price_paths * np.exp(q * np.arange(1, n_obs + 1) * dt)                           # total return (dividendes réinvestis)
    cpn = p.coupon_annuel * dt
    alive = np.ones(n_paths, dtype=bool)
    owed = np.zeros(n_paths)
    cash = np.zeros(n_paths)
    end_t = np.full(n_paths, float(p.maturite))
    for i in range(n_obs):
        t = (i + 1) * dt
        s = price_paths[:, i]
        pay = alive & (s >= p.barriere_coupon)
        cash += np.where(pay, cpn + (owed if p.memoire else 0.0), 0.0) * p.nominal
        owed = np.where(alive & ~pay, owed + cpn, np.where(pay, 0.0, owed))
        if i + 1 >= p.premiere_obs_rappel:
            call = alive & (s >= p.barriere_rappel)
            cash += np.where(call, p.nominal, 0.0)
            end_t[call] = t
            alive &= ~call
    sT = price_paths[:, -1]
    cash += np.where(alive, np.where(sT >= p.barriere_capital, 1.0, sT) * p.nominal, 0.0)
    # TRI approximé par (cash/nominal)^(1/duree)-1 (coupons non réinvestis, simplification documentée)
    irr_prod = (cash / p.nominal) ** (1 / end_t) - 1
    irr_idx = paths[:, -1] ** (1 / p.maturite) - 1
    return {
        "tri_produit_moyen": float(irr_prod.mean()), "tri_produit_median": float(np.median(irr_prod)),
        "tri_indice_moyen": float(irr_idx.mean()), "tri_indice_median": float(np.median(irr_idx)),
        "proba_produit_bat_indice": float((irr_prod > irr_idx).mean()),
        "pire_5pct_produit": float(np.percentile(irr_prod, 5)), "pire_5pct_indice": float(np.percentile(irr_idx, 5)),
    }


def fair_coupon(p: Autocall, cible_prix_pct: float = 98.0, **kw) -> float:
    """Coupon annuel tel que le prix du produit = `cible_prix_pct` (100 - marge de l'émetteur).
    Recherche dichotomique ; mêmes aléas (graine fixe) pour une fonction monotone."""
    lo, hi = 0.0, 0.5
    for _ in range(40):
        mid = (lo + hi) / 2
        q = Autocall(**{**p.__dict__, "coupon_annuel": mid})
        if price_autocall(q, **kw)["prix_pct_nominal"] < cible_prix_pct:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2
