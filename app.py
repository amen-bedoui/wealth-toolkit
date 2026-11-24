"""Application Streamlit : streamlit run app.py"""
import os
import tempfile
import pandas as pd
import streamlit as st
from wealth import planner, portfolio, structured, tax, data, market_data, report

st.set_page_config(page_title="Wealth Toolkit", layout="wide")
CALIBRATED = data.load_calibration()   # hypothèses calibrées sur données réelles si `wealth backtest` a été lancé
st.title("Wealth Toolkit")
st.caption("Outil pédagogique, ne constitue pas un conseil en investissement. Hypothèses de marché : "
           + ("calibrées sur données réelles (50 % historique, 50 % long terme)." if CALIBRATED else "illustratives de long terme."))

eur = lambda x: f"{x:,.0f} €".replace(",", " ")
pct = lambda x, d=1: f"{x * 100:.{d}f} %".replace(".", ",")


@st.cache_data(show_spinner=False)
def run_projection(weights_tuple, patrimoine, versement, inflation, frais, n_years, n_paths):
    w = pd.Series(dict(weights_tuple))
    sc = planner.Scenario(patrimoine, versement, inflation=inflation, frais_annuels=frais)
    return planner.project(w, sc, n_years, n_paths)


tab1, tab2, tab3, tab4 = st.tabs(["Projection patrimoniale", "Suivi de portefeuille", "Produits structurés", "Fiscalité et transmission"])

# ---------------- Projection ----------------
with tab1:
    c1, c2, c3 = st.columns(3)
    with c1:
        st.subheader("Profil")
        horizon = st.slider("Horizon d'investissement (ans)", 1, 30, 15)
        loss = st.select_slider("Tolérance aux pertes", [1, 2, 3, 4], 3, format_func=lambda x: {1: "faible", 2: "modérée", 3: "élevée", 4: "très élevée"}[x])
        exp = st.select_slider("Expérience des marchés", [1, 2, 3, 4], 2)
        stab = st.select_slider("Stabilité des revenus", [1, 2, 3, 4], 3)
        profile = planner.risk_profile(horizon, loss, exp, stab)
        profile = st.selectbox("Profil retenu", planner.PROFILES, planner.PROFILES.index(profile))
    with c2:
        st.subheader("Situation")
        patrimoine = st.number_input("Patrimoine initial (€)", 0, 100_000_000, 500_000, 10_000)
        versement = st.number_input("Versement annuel (€)", 0, 10_000_000, 20_000, 1_000)
        inflation = st.slider("Inflation (%)", 0.0, 5.0, 2.0, 0.1) / 100
        frais = st.slider("Frais annuels totaux (%)", 0.0, 3.0, 1.0, 0.05) / 100
    with c3:
        st.subheader("Objectif")
        goal_name = st.text_input("Nom", "Capital de transmission")
        goal_amt = st.number_input("Montant (€ d'aujourd'hui)", 0, 100_000_000, 1_000_000, 50_000)
        goal_years = st.slider("Dans (ans)", 1, 30, min(horizon, 30))
    w = planner.target_allocation(profile)
    n_years = max(goal_years, 20)
    paths = run_projection(tuple(w.items()), patrimoine, versement, inflation, frais, n_years, 10_000)
    goal = planner.Goal(goal_name, goal_amt, goal_years)
    prob = planner.goal_probability(paths, goal, inflation)
    stats = planner.portfolio_stats(w)
    summ = planner.summarize(paths, inflation)
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Probabilité d'atteindre l'objectif", pct(prob, 0))
    m2.metric("Rendement espéré", pct(stats["rendement_espere"]))
    m3.metric("Volatilité", pct(stats["volatilite"]))
    m4.metric("Patrimoine réel médian à l'horizon", eur(summ.iloc[goal_years]["P50"]))
    cl, cr = st.columns([1, 2])
    cl.subheader("Allocation cible")
    cl.dataframe(w[w > 0].map(lambda x: pct(x, 0)).rename("Poids"), use_container_width=True)
    cr.subheader("Projection (euros d'aujourd'hui)")
    cr.line_chart(summ[["P5", "P25", "P50", "P75", "P95"]])
    if st.button("Exporter le rapport PDF"):
        need = planner.required_contribution(w, planner.Scenario(patrimoine, versement, inflation=inflation, frais_annuels=frais), goal, 0.7, n_paths=3000)
        prem = patrimoine + sum(versement * (1 + inflation) ** t for t in range(goal_years))
        tmp = os.path.join(tempfile.mkdtemp(), "projection.pdf")
        report.planner_report(tmp, {"nom": "Client"}, profile, w, stats, summ, prob, goal, need,
                              tax_cmp=tax.compare_envelopes(paths, prem, goal_years, inflation))
        st.download_button("Télécharger le PDF", open(tmp, "rb").read(), "projection_patrimoniale.pdf", "application/pdf")

# ---------------- Portefeuille ----------------
with tab2:
    st.subheader("Suivi de portefeuille")
    src = st.radio("Source des données", ["Données réelles en cache (wealth fetch)", "Import CSV", "Données simulées (démo)"], index=2, horizontal=True)
    hist, label = None, ""
    try:
        if src.startswith("Données réelles"):
            hist, label = market_data.monthly_returns(market_data.fetch_prices()), "réelles"
        elif src == "Import CSV":
            up = st.file_uploader("Fichier CSV (dates en 1re colonne, une colonne par ligne du portefeuille)", type=["csv"])
            kind = st.radio("Contenu", ["prices", "returns"], horizontal=True, format_func=lambda x: "cours / valorisations" if x == "prices" else "rendements mensuels")
            if up is not None:
                tmp = os.path.join(tempfile.mkdtemp(), "pf.csv")
                open(tmp, "wb").write(up.getvalue())
                hist, label = market_data.load_csv(tmp, kind=kind), "importées"
        else:
            hist, label = data.synthetic_history(n_months=60), "SIMULÉES"
    except Exception as e:
        st.error(f"Impossible de charger les données : {e}")
    if hist is not None:
        st.caption(f"Données {label} : {hist.index[0].date()} → {hist.index[-1].date()}, {len(hist)} mois.")
        cols = list(hist.columns)
        default = pd.Series(1 / len(cols), index=cols)
        edited = st.data_editor(default.rename("Poids actuel").to_frame(), use_container_width=True)["Poids actuel"]
        if abs(edited.sum() - 1) > 1e-6:
            st.warning(f"Les poids somment à {edited.sum():.2%} : ajuste-les à 100 %.")
        else:
            bench_prof = st.selectbox("Benchmark : allocation du profil", planner.PROFILES, 1)
            bw = planner.target_allocation(bench_prof)
            bw = bw[bw.index.isin(cols)]
            bw = bw / bw.sum()
            r = portfolio.portfolio_returns(hist, edited)
            bench = portfolio.portfolio_returns(hist[bw.index], bw)
            s = portfolio.summary(r, bench)
            a, b, c, d = st.columns(4)
            a.metric("Rendement annualisé", pct(s["rendement_annualise"])); b.metric("Volatilité", pct(s["volatilite"]))
            c.metric("Sharpe", f"{s['sharpe']:.2f}"); d.metric("Drawdown max", pct(s["max_drawdown"]))
            st.line_chart(pd.DataFrame({"Portefeuille": portfolio.cumulative(r) * 100, "Benchmark": portfolio.cumulative(bench) * 100}))
            total = st.number_input("Valeur totale du portefeuille (€)", 1_000, 1_000_000_000, 2_000_000, 50_000)
            band = st.slider("Bande de tolérance (points)", 1, 10, 3) / 100
            tr = portfolio.rebalancing_trades(edited * total, bw, band)
            st.dataframe(tr.assign(**{c: tr[c].map(lambda x: pct(x)) for c in ["actuel", "cible", "ecart"]}), use_container_width=True)
            st.info("Rééquilibrage nécessaire." if tr.attrs["rebalance"] else "Aucune ligne ne dépasse la bande de tolérance.")

# ---------------- Produits structurés ----------------
with tab3:
    kind = st.radio("Produit", ["Autocall / Phoenix", "Reverse convertible à barrière", "Capital protégé"], horizontal=True)
    sigma = st.slider("Volatilité de l'indice (%)", 5, 50, 18) / 100
    rate = st.slider("Taux sans risque (%)", 0.0, 6.0, 2.5, 0.1) / 100
    div = st.slider("Rendement du dividende (%)", 0.0, 6.0, 3.0, 0.1) / 100
    if kind == "Autocall / Phoenix":
        c = st.columns(5)
        mat = c[0].slider("Maturité (ans)", 2, 12, 8)
        rap = c[1].slider("Barrière de rappel (%)", 80, 120, 100) / 100
        bc = c[2].slider("Barrière de coupon (%)", 40, 100, 70) / 100
        bk = c[3].slider("Barrière de capital (%)", 30, 100, 60) / 100
        mem = c[4].checkbox("Effet mémoire", True)
        a0 = structured.Autocall(maturite=mat, barriere_rappel=rap, barriere_coupon=bc, barriere_capital=min(bk, bc), memoire=mem)
        margin = st.slider("Marge de l'émetteur (% du nominal)", 0.0, 6.0, 2.0, 0.5)
        fc = structured.fair_coupon(a0, 100 - margin, r=rate, q=div, sigma=sigma, n_paths=15_000)
        a0 = structured.Autocall(**{**a0.__dict__, "coupon_annuel": fc})
        res = structured.price_autocall(a0, r=rate, q=div, sigma=sigma, n_paths=30_000)
        cmp_ = structured.compare_with_underlying(a0, r=rate, q=div, sigma=sigma)
        x = st.columns(4)
        x[0].metric("Coupon annuel juste", pct(fc)); x[1].metric("Proba. de perte en capital", pct(res["proba_perte_capital"]))
        x[2].metric("Durée de vie moyenne", f"{res['duree_vie_moyenne_annees']:.1f} ans"); x[3].metric("Proba. de battre l'indice", pct(cmp_["proba_produit_bat_indice"], 0))
        st.bar_chart(pd.Series(res["proba_rappel_cumulee"], name="Rappel cumulé"))
        st.dataframe(pd.DataFrame({"Produit": [cmp_["tri_produit_moyen"], cmp_["tri_produit_median"], cmp_["pire_5pct_produit"]],
                                   "Indice": [cmp_["tri_indice_moyen"], cmp_["tri_indice_median"], cmp_["pire_5pct_indice"]]},
                                  index=["TRI moyen", "TRI médian", "Pire 5 %"]).map(pct))
    elif kind == "Reverse convertible à barrière":
        c = st.columns(3)
        mat = c[0].slider("Maturité (ans)", 0.5, 3.0, 1.0, 0.5)
        bar = c[1].slider("Barrière (%)", 40, 90, 70) / 100
        margin = c[2].slider("Marge de l'émetteur (%)", 0.0, 6.0, 2.0, 0.5)
        rc0 = structured.ReverseConvertible(maturite=mat, barriere=bar)
        fc = structured.fair_rc_coupon(rc0, 100 - margin, r=rate, q=div, sigma=sigma, n_paths=15_000)
        rc = structured.ReverseConvertible(maturite=mat, barriere=bar, coupon_annuel=fc)
        res = structured.price_reverse_convertible(rc, r=rate, q=div, sigma=sigma, n_paths=30_000)
        cmp_ = structured.compare_rc_with_underlying(rc, q=div, sigma=sigma)
        x = st.columns(4)
        x[0].metric("Coupon annuel juste", pct(fc)); x[1].metric("Proba. de knock-in", pct(res["proba_knock_in"]))
        x[2].metric("Proba. de perte en capital", pct(res["proba_perte_capital"])); x[3].metric("Proba. de battre l'indice", pct(cmp_["proba_produit_bat_indice"], 0))
        st.dataframe(pd.DataFrame({"Produit": [cmp_["rendement_produit_moyen"], cmp_["rendement_produit_median"], cmp_["pire_5pct_produit"]],
                                   "Indice": [cmp_["rendement_indice_moyen"], cmp_["rendement_indice_median"], cmp_["pire_5pct_indice"]]},
                                  index=["Rendement moyen", "Rendement médian", "Pire 5 %"]).map(pct))
    else:
        mat = st.slider("Maturité (ans)", 2, 10, 6)
        prot = st.slider("Protection du capital (%)", 80, 100, 100) / 100
        spread = st.slider("Spread de crédit de l'émetteur (%)", 0.0, 3.0, 0.0, 0.1) / 100
        res = structured.price_capital_protege(structured.CapitalProtege(maturite=mat, protection=prot), r=rate, q=div, sigma=sigma, taux_emetteur_spread=spread)
        x = st.columns(3)
        x[0].metric("Zéro-coupon", pct(res["valeur_zero_coupon_pct"] / 100)); x[1].metric("Budget d'option", pct(res["budget_option_pct"] / 100))
        x[2].metric("Participation à la hausse", pct(res["participation_pct"] / 100, 0))

# ---------------- Fiscalité ----------------
with tab4:
    st.caption(f"Barèmes 2026 simplifiés, validés au {tax.validity_date()}. Voir tax_params.json et ses sources officielles.")
    st.subheader("Enveloppes : patrimoine net d'impôt")
    g = st.number_input("Gain réalisé (€)", 0, 100_000_000, 100_000, 10_000)
    yrs = st.slider("Durée de détention (ans)", 1, 30, 10)
    prem = st.number_input("Primes / versements cumulés (€)", 1, 100_000_000, 300_000, 10_000)
    couple = st.checkbox("Couple (abattement assurance-vie doublé)")
    st.dataframe(pd.DataFrame({e: {"Impôt + prélèvements": eur(float(tax.tax_on_gain(g, e, yrs, prem, couple=couple))),
                                   "Taux effectif": pct(float(tax.tax_on_gain(g, e, yrs, prem, couple=couple)) / g if g else 0)}
                               for e in tax.ENVELOPPES}))
    st.subheader("Transmission")
    c = st.columns(3)
    amt = c[0].number_input("Montant transmis (€)", 0, 100_000_000, 500_000, 50_000)
    rel = c[1].selectbox("Lien", ["ligne_directe", "freres_soeurs", "neveux_nieces", "tiers", "conjoint"])
    used = c[2].number_input("Abattement déjà utilisé (€)", 0, 100_000, 0, 10_000)
    fr, mc = tax.inheritance_tax(amt, rel, "France", used), tax.inheritance_tax(amt, rel, "Monaco")
    st.dataframe(pd.DataFrame({"France": {"Droits": eur(fr["droits"]), "Taux effectif": pct(fr["taux_effectif"])},
                               "Monaco": {"Droits": eur(mc["droits"]), "Taux effectif": pct(mc["taux_effectif"])}}))
    st.warning("Monaco : hypothèses très simplifiées (biens situés à Monaco, résident non français). À valider avec un fiscaliste.")
