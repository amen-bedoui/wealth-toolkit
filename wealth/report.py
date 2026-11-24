"""Rapports PDF (reportlab) et graphiques (matplotlib)."""
from __future__ import annotations
import io
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image

NAVY = "#1f3a5f"
_ss = getSampleStyleSheet()
H1 = ParagraphStyle("H1", parent=_ss["Heading1"], textColor=colors.HexColor(NAVY), fontSize=18, spaceAfter=6)
H2 = ParagraphStyle("H2", parent=_ss["Heading2"], textColor=colors.HexColor(NAVY), fontSize=12, spaceBefore=10, spaceAfter=4)
P = ParagraphStyle("P", parent=_ss["BodyText"], fontSize=9.5, leading=13)
SMALL = ParagraphStyle("S", parent=P, fontSize=7.5, leading=10, textColor=colors.grey)


def pct(x, d=1):
    return f"{x * 100:.{d}f} %".replace(".", ",")


def eur(x):
    return f"{x:,.0f} €".replace(",", " ")


def _img(fig, width=16 * cm):
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=160, bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    im = Image(buf)
    ratio = im.imageHeight / im.imageWidth
    im.drawWidth, im.drawHeight = width, width * ratio
    return im


def _table(rows, col_widths=None, header=True):
    t = Table(rows, colWidths=col_widths, hAlign="LEFT")
    st = [("FONTSIZE", (0, 0), (-1, -1), 8.5), ("GRID", (0, 0), (-1, -1), 0.25, colors.lightgrey),
          ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f3f6fa")])]
    if header:
        st += [("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(NAVY)), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
               ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold")]
    t.setStyle(TableStyle(st))
    return t


DISCLAIMER = ("Document pédagogique généré par un projet open source. Les projections reposent sur des hypothèses de marché illustratives ; "
              "les données historiques éventuelles proviennent de sources publiques (ETF cotés). Ne constitue ni un conseil en investissement "
              "ni un conseil fiscal, ni une offre. Les performances passées ou simulées ne préjugent pas des performances futures.")


def planner_report(path, client: dict, profile: str, weights: pd.Series, stats: dict, summary: pd.DataFrame,
                   prob: float, goal, contribution_needed: float, tax_cmp: dict | None = None, succession: list | None = None):
    from .data import CMA
    doc = SimpleDocTemplate(path, pagesize=A4, leftMargin=2 * cm, rightMargin=2 * cm, topMargin=1.8 * cm, bottomMargin=1.6 * cm)
    el = [Paragraph("Projection patrimoniale", H1),
          Paragraph(f"Client : {client.get('nom', 'Client exemple')} — Profil de risque : <b>{profile}</b>", P),
          Paragraph("1. Allocation cible", H2)]
    rows = [["Classe d'actifs", "Poids", "Rendement espéré", "Volatilité"]]
    for a, w in weights[weights > 0].items():
        rows.append([a, pct(w, 0), pct(CMA.loc[a, "rendement"]), pct(CMA.loc[a, "volatilite"])])
    rows.append(["Portefeuille", "100 %", pct(stats["rendement_espere"]), pct(stats["volatilite"])])
    el.append(_table(rows, [7 * cm, 2.5 * cm, 4 * cm, 3 * cm]))
    fig, ax = plt.subplots(figsize=(6, 2.6))
    ww = weights[weights > 0]
    ax.barh(ww.index[::-1], ww.values[::-1] * 100, color=NAVY)
    ax.set_xlabel("Poids (%)")
    ax.spines[["top", "right"]].set_visible(False)
    el += [Spacer(1, 6), _img(fig, 12 * cm), Paragraph("2. Projection du patrimoine (euros d'aujourd'hui)", H2)]
    fig, ax = plt.subplots(figsize=(7, 3.3))
    x = summary.index
    ax.fill_between(x, summary["P5"], summary["P95"], color=NAVY, alpha=0.12, label="P5 – P95")
    ax.fill_between(x, summary["P25"], summary["P75"], color=NAVY, alpha=0.28, label="P25 – P75")
    ax.plot(x, summary["P50"], color=NAVY, lw=2, label="Médiane")
    ax.axhline(goal.montant_cible, color="#b5392b", ls="--", lw=1, label=f"Objectif {eur(goal.montant_cible)}")
    ax.set_xlabel("Années"); ax.set_ylabel("€")
    ax.xaxis.set_major_locator(matplotlib.ticker.MaxNLocator(integer=True))
    ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: f"{v / 1e6:.1f} M"))
    ax.legend(frameon=False, fontsize=8); ax.spines[["top", "right"]].set_visible(False)
    el.append(_img(fig))
    last = summary.iloc[goal.horizon_annees]
    el += [Paragraph(f"3. Objectif : {goal.nom}", H2),
           Paragraph(f"Objectif de <b>{eur(goal.montant_cible)}</b> (euros d'aujourd'hui) à {goal.horizon_annees} ans. "
                     f"Probabilité d'atteinte : <b>{pct(prob, 0)}</b>. Patrimoine réel à l'horizon : médiane {eur(last['P50'])}, "
                     f"scénario défavorable (P5) {eur(last['P5'])}, scénario favorable (P95) {eur(last['P95'])}.", P),
           Paragraph(f"Versement annuel nécessaire pour 70 % de chances d'atteindre l'objectif : <b>{eur(contribution_needed)}</b>.", P),
           ]
    if tax_cmp:
        from .tax import validity_date
        el.append(Paragraph("4. Patrimoine net d'impôt selon l'enveloppe (euros d'aujourd'hui)", H2))
        rows = [["Enveloppe", "Défavorable (P5)", "Médian", "Favorable (P95)", "Poids fiscal médian"]]
        for env, v in tax_cmp.items():
            rows.append([env, eur(v["P5"]), eur(v["P50"]), eur(v["P95"]), pct(v["poids_fiscal_median"])])
        el.append(_table(rows, [4.5 * cm, 3.2 * cm, 3 * cm, 3.2 * cm, 3.2 * cm]))
        el.append(Paragraph(f"Liquidation totale à l'horizon, flat tax et prélèvements sociaux 2026 (barèmes au {validity_date()}). "
                            "Hypothèses simplifiées, voir le README.", SMALL))
    if succession:
        el.append(Paragraph("5. Transmission : droits selon le lieu de résidence", H2))
        rows = [["Montant", "Lien", "Droits en France", "Droits à Monaco"]] + succession
        el.append(_table(rows, [3.5 * cm, 4 * cm, 4.5 * cm, 4.5 * cm]))
    el += [Spacer(1, 10), Paragraph(DISCLAIMER, SMALL)]
    doc.build(el)


def portfolio_report(path, name: str, r: pd.Series, bench: pd.Series, summ: dict, drift_df: pd.DataFrame,
                     risk_contrib: pd.Series, trades: pd.DataFrame):
    from .portfolio import cumulative
    doc = SimpleDocTemplate(path, pagesize=A4, leftMargin=2 * cm, rightMargin=2 * cm, topMargin=1.8 * cm, bottomMargin=1.6 * cm)
    el = [Paragraph("Rapport de suivi de portefeuille", H1), Paragraph(f"Portefeuille : <b>{name}</b>", P),
          Paragraph("1. Performance et risque", H2)]
    rows = [["Indicateur", "Valeur"],
            ["Rendement annualisé", pct(summ["rendement_annualise"])], ["Volatilité annualisée", pct(summ["volatilite"])],
            ["Ratio de Sharpe", f"{summ['sharpe']:.2f}".replace(".", ",")], ["Perte maximale (drawdown)", pct(summ["max_drawdown"])],
            ["VaR 95 % mensuelle", pct(summ["VaR_95_mensuelle"])], ["CVaR 95 % mensuelle", pct(summ["CVaR_95_mensuelle"])]]
    if "beta" in summ:
        rows += [["Bêta vs benchmark", f"{summ['beta']:.2f}".replace(".", ",")], ["Tracking error", pct(summ["tracking_error"])],
                 ["Information ratio", f"{summ['information_ratio']:.2f}".replace(".", ",")]]
    el.append(_table(rows, [7 * cm, 4 * cm]))
    fig, ax = plt.subplots(figsize=(7, 3))
    ax.plot(cumulative(r) * 100, color=NAVY, lw=2, label="Portefeuille")
    ax.plot(cumulative(bench) * 100, color="#888", lw=1.5, label="Benchmark")
    ax.legend(frameon=False, fontsize=8); ax.set_ylabel("Base 100"); ax.spines[["top", "right"]].set_visible(False)
    el += [Spacer(1, 6), _img(fig), Paragraph("2. Allocation et dérive vs cible", H2)]
    rows = [["Classe d'actifs", "Actuel", "Cible", "Écart", "Contrib. risque"]]
    for a, row in drift_df.iterrows():
        rc = risk_contrib.get(a, np.nan)
        rows.append([a, pct(row["actuel"]), pct(row["cible"]), pct(row["ecart"]), "" if pd.isna(rc) else pct(rc, 0)])
    el.append(_table(rows, [6 * cm, 2.5 * cm, 2.5 * cm, 2.5 * cm, 3 * cm]))
    el.append(Paragraph("3. Rééquilibrage", H2))
    if trades.attrs.get("rebalance"):
        rows = [["Classe d'actifs", "Montant à traiter"]] + [[a, eur(v)] for a, v in trades["montant_a_trader"].items() if abs(v) > 1]
        el.append(_table(rows, [7 * cm, 4 * cm]))
    else:
        el.append(Paragraph("Aucune ligne ne dépasse la bande de tolérance : pas de rééquilibrage nécessaire.", P))
    el += [Spacer(1, 10), Paragraph(DISCLAIMER, SMALL)]
    doc.build(el)


def structured_report(path, autocall, price: dict, fair_cpn: float, comparison: dict, cp: dict, rc=None):
    doc = SimpleDocTemplate(path, pagesize=A4, leftMargin=2 * cm, rightMargin=2 * cm, topMargin=1.8 * cm, bottomMargin=1.6 * cm)
    a = autocall
    el = [Paragraph("Analyse de produits structurés", H1), Paragraph("1. Autocall à coupons conditionnels (effet mémoire)", H2),
          Paragraph(f"Maturité {a.maturite} ans, rappel si indice ≥ {pct(a.barriere_rappel, 0)}, coupon {pct(a.coupon_annuel)} par an si indice ≥ "
                    f"{pct(a.barriere_coupon, 0)}, protection du capital jusqu'à {pct(1 - a.barriere_capital, 0)} de baisse à l'échéance.", P)]
    rows = [["Mesure", "Valeur"], ["Valeur théorique du produit", pct(price["prix_pct_nominal"] / 100)],
            ["Coupon qui laisserait 2 % de marge à l'émetteur", pct(fair_cpn)],
            ["Probabilité de perte en capital", pct(price["proba_perte_capital"])],
            ["Perte moyenne si perte", pct(price["perte_moyenne_si_perte_pct"] / 100, 0)],
            ["Durée de vie moyenne", f"{price['duree_vie_moyenne_annees']:.1f} ans".replace(".", ",")]]
    el.append(_table(rows, [9 * cm, 4 * cm]))
    ys = list(price["proba_rappel_cumulee"].keys())
    fig, ax = plt.subplots(figsize=(6, 2.6))
    ax.bar(ys, [price["proba_rappel_cumulee"][y] * 100 for y in ys], color=NAVY)
    ax.set_xlabel("Année"); ax.set_ylabel("Rappel cumulé (%)"); ax.spines[["top", "right"]].set_visible(False)
    el += [Spacer(1, 6), _img(fig, 11 * cm), Paragraph("2. Produit vs indice détenu en direct (monde réel, drift 7 %)", H2)]
    rows = [["", "Produit", "Indice (div. réinv.)"],
            ["TRI moyen", pct(comparison["tri_produit_moyen"]), pct(comparison["tri_indice_moyen"])],
            ["TRI médian", pct(comparison["tri_produit_median"]), pct(comparison["tri_indice_median"])],
            ["Pire 5 % des cas", pct(comparison["pire_5pct_produit"]), pct(comparison["pire_5pct_indice"])]]
    el.append(_table(rows, [6 * cm, 4 * cm, 5 * cm]))
    el.append(Paragraph(f"Probabilité que le produit batte l'indice : <b>{pct(comparison['proba_produit_bat_indice'], 0)}</b>. "
                        "Le produit échange du potentiel de hausse contre un rendement plus régulier et une protection partielle ; "
                        "il porte aussi un risque émetteur et un risque de liquidité non modélisés ici.", P))
    el += [Paragraph("3. Note à capital protégé", H2),
           Paragraph(f"Décomposition : zéro-coupon {pct(cp['valeur_zero_coupon_pct'] / 100)} + budget d'option {pct(cp['budget_option_pct'] / 100)}. "
                     f"Avec un call ATM à {pct(cp['prix_call_atm_pct'] / 100)}, la participation à la hausse est de {pct(cp['participation_pct'] / 100, 0)} "
                     "(avant marge de l'émetteur).", P)]
    if rc:
        p, pr, fair, cmp_ = rc["produit"], rc["prix"], rc["coupon_juste"], rc["comparaison"]
        el += [Paragraph("4. Reverse convertible à barrière", H2),
               Paragraph(f"Maturité {p.maturite:g} an, barrière de knock-in à {pct(p.barriere, 0)} (observation quotidienne). Coupon qui laisserait 2 % de marge à "
                         f"l'émetteur : <b>{pct(fair)}</b> par an. Probabilité de touche de la barrière : {pct(pr['proba_knock_in'])}, "
                         f"probabilité de perte en capital : {pct(pr['proba_perte_capital'])} (perte moyenne {pct(pr['perte_moyenne_si_perte_pct'] / 100, 0)}).", P)]
        rows = [["", "Produit", "Indice (div. réinv.)"],
                ["Rendement moyen", pct(cmp_["rendement_produit_moyen"]), pct(cmp_["rendement_indice_moyen"])],
                ["Rendement médian", pct(cmp_["rendement_produit_median"]), pct(cmp_["rendement_indice_median"])],
                ["Pire 5 % des cas", pct(cmp_["pire_5pct_produit"]), pct(cmp_["pire_5pct_indice"])]]
        el += [_table(rows, [6 * cm, 4 * cm, 5 * cm]),
               Paragraph(f"Probabilité que le produit batte l'indice : <b>{pct(cmp_['proba_produit_bat_indice'], 0)}</b>. "
                         "Le coupon est fixe mais le capital est exposé en dessous de la barrière : l'investisseur vend un put.", P)]
    el += [Spacer(1, 10), Paragraph(DISCLAIMER, SMALL)]
    doc.build(el)
