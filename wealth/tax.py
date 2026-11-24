"""Fiscalité simplifiée France / Monaco : enveloppes d'épargne (liquidation) et droits de succession/donation.

Les paramètres sont dans `tax_params.json` (datés, avec sources officielles). Hypothèses simplifiées :
- la fiscalité est appliquée à la LIQUIDATION totale à l'horizon (pas de fiscalité au fil de l'eau) ;
- gain = patrimoine final - versements cumulés (nominal) ;
- un seul contribuable, pas de barème progressif de l'IR (flat tax / PFU) ;
- l'abattement annuel de l'assurance-vie n'est utilisé qu'une fois (rachat total en une seule année).
"""
from __future__ import annotations
import json
import os
from functools import lru_cache
import numpy as np

ENVELOPPES = ["CTO", "PEA", "Assurance-vie", "Résident monégasque"]
_PATH = os.path.join(os.path.dirname(__file__), "tax_params.json")


@lru_cache(maxsize=1)
def params() -> dict:
    with open(_PATH, encoding="utf-8") as f:
        return json.load(f)


def validity_date() -> str:
    return params()["date_validite"]


def tax_on_gain(gain, envelope: str, years_held: float, total_premiums: float = 0.0, couple: bool = False):
    """Impôt + prélèvements sociaux dus sur un gain (scalaire ou tableau numpy) au rachat/cession total."""
    if envelope not in ENVELOPPES:
        raise ValueError(f"enveloppe inconnue : {envelope}")
    p = params()["france"]
    g = np.maximum(np.asarray(gain, dtype=float), 0.0)          # pas d'impôt sur une moins-value
    if envelope == "CTO":
        return g * (p["ir_pfu"] + p["ps_standard"])
    if envelope == "PEA":
        ir = 0.0 if years_held >= p["pea"]["seuil_exoneration_ir_ans"] else p["ir_pfu"]
        return g * (ir + p["ps_standard"])
    if envelope == "Assurance-vie":
        av = p["assurance_vie"]
        ps = g * p["ps_assurance_vie"]
        if years_held < av["seuil_8_ans"]:
            return ps + g * av["taux_avant_8_ans"]
        abatt = av["abattement_annuel_couple"] if couple else av["abattement_annuel_seul"]
        base_ir = np.maximum(g - abatt, 0.0)
        taux = av["taux_apres_8_ans_primes_inf_150k"] if total_premiums <= av["seuil_primes"] else av["taux_apres_8_ans_primes_sup_150k"]
        if total_premiums > av["seuil_primes"]:
            # proratisation : la part des produits liée aux primes <= 150 k€ reste à 7,5 %
            part_basse = av["seuil_primes"] / total_premiums
            taux = part_basse * av["taux_apres_8_ans_primes_inf_150k"] + (1 - part_basse) * av["taux_apres_8_ans_primes_sup_150k"]
        return ps + base_ir * taux
    # Résident monégasque non français : hypothèse documentée dans tax_params.json
    m = params()["monaco_resident_non_francais"]
    return g * (m["ir_revenus_capital"] + m["ps"])


def net_of_tax(wealth_paths: np.ndarray, total_premiums: float, envelope: str, horizon: int, **kw) -> np.ndarray:
    """Patrimoine net d'impôt à l'horizon, pour chaque trajectoire Monte Carlo (liquidation totale)."""
    final = wealth_paths[:, horizon]
    gain = final - total_premiums
    return final - tax_on_gain(gain, envelope, horizon, total_premiums, **kw)


def compare_envelopes(wealth_paths: np.ndarray, total_premiums: float, horizon: int, inflation: float = 0.02,
                      envelopes=None, **kw) -> dict:
    """Patrimoine net d'impôt (euros d'aujourd'hui) par enveloppe : médiane, P5, P95, et taux d'imposition effectif médian."""
    out = {}
    deflator = (1 + inflation) ** horizon
    for env in envelopes or ENVELOPPES:
        net = net_of_tax(wealth_paths, total_premiums, env, horizon, **kw)
        gross = wealth_paths[:, horizon]
        eff = 1 - np.median(net) / np.median(gross)
        out[env] = {"P5": float(np.percentile(net, 5) / deflator), "P50": float(np.median(net) / deflator),
                    "P95": float(np.percentile(net, 95) / deflator), "poids_fiscal_median": float(eff)}
    return out


def _progressive(amount: float, bareme: list) -> float:
    tax, lower = 0.0, 0.0
    for upper, rate in bareme:
        top = amount if upper is None else min(amount, upper)
        if top > lower:
            tax += (top - lower) * rate
        if upper is None or amount <= upper:
            break
        lower = upper
    return tax


def inheritance_tax(amount: float, relation: str, residence: str = "France", already_used_allowance: float = 0.0) -> dict:
    """Droits de succession/donation sur la part d'un héritier.
    relation : 'ligne_directe' | 'freres_soeurs' | 'neveux_nieces' | 'tiers' | 'conjoint'.
    residence : 'France' (barème français) ou 'Monaco' (taux monégasques, ligne directe et conjoint exonérés).
    `already_used_allowance` : abattement déjà consommé par des donations de moins de 15 ans au même bénéficiaire."""
    if amount < 0:
        raise ValueError("montant négatif")
    if residence == "Monaco":
        m = params()["succession_monaco"]
        key = {"conjoint": "conjoint", "ligne_directe": "ligne_directe", "freres_soeurs": "freres_soeurs"}.get(relation, "tiers")
        rate = m[key]["taux"]
        return {"abattement": 0.0, "base_taxable": amount, "droits": amount * rate, "taux_effectif": rate}
    if residence != "France":
        raise ValueError("residence doit valoir 'France' ou 'Monaco'")
    s = params()["succession_france"]
    if relation == "conjoint":
        return {"abattement": amount, "base_taxable": 0.0, "droits": 0.0, "taux_effectif": 0.0}
    if relation not in ("ligne_directe", "freres_soeurs", "neveux_nieces", "tiers"):
        raise ValueError(f"lien inconnu : {relation}")
    cfg = s[relation]
    abatt = max(cfg["abattement"] - already_used_allowance, 0.0)
    base = max(amount - abatt, 0.0)
    droits = _progressive(base, cfg["bareme"]) if "bareme" in cfg else base * cfg["taux"]
    return {"abattement": min(abatt, amount), "base_taxable": base, "droits": droits, "taux_effectif": droits / amount if amount else 0.0}


def donation_plan(amount_per_child: float, n_children: int = 2, parents: int = 2, years: int = 30) -> dict:
    """Combien de donations (tous les 15 ans) pour transmettre sans droits ? Illustration simple en ligne directe, France.
    Chaque parent dispose de l'abattement par enfant, renouvelé tous les 15 ans."""
    a = params()["succession_france"]["ligne_directe"]["abattement"]
    renouvellements = years // params()["succession_france"]["donation"]["periode_rappel_ans"] + 1
    exempt = a * parents * renouvellements
    return {"abattement_par_enfant_par_parent": a, "renouvellements": renouvellements,
            "montant_exonere_par_enfant": exempt,
            "montant_a_transmettre_par_enfant": amount_per_child,
            "reste_taxable_par_enfant": max(amount_per_child - exempt, 0.0),
            "n_enfants": n_children}
