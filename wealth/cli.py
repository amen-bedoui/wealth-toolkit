"""Ligne de commande : python -m wealth demo --out reports"""
from __future__ import annotations
import argparse, os
import pandas as pd
from . import planner, portfolio, structured, report, data, market_data, backtest


def _history(real: bool, cache_dir: str = "data"):
    """Historique mensuel : réel (cache CSV déjà téléchargé par `wealth fetch`) ou, à défaut, simulé et étiqueté comme tel."""
    import os
    path = os.path.join(cache_dir, "prices.csv")
    if real:
        if not os.path.exists(path):
            raise SystemExit("Pas de données réelles : lance d'abord `python -m wealth fetch`.")
        r = market_data.monthly_returns(market_data.fetch_prices(cache_dir=cache_dir))
        return r, "données réelles (ETF cotés, dividendes réinvestis)"
    return data.synthetic_history(n_months=60), "données SIMULÉES"


def run_demo(out: str = "reports", real: bool = False):
    os.makedirs(out, exist_ok=True)
    # 1. Planificateur
    prof = planner.risk_profile(horizon_years=15, loss_tolerance=3, experience=2, income_stability=3)
    w = planner.target_allocation(prof)
    stats = planner.portfolio_stats(w)
    sc = planner.Scenario(patrimoine_initial=500_000, versement_annuel=20_000, inflation=0.02, frais_annuels=0.01)
    goal = planner.Goal("Capital de transmission", 1_000_000, 15)
    paths = planner.project(w, sc, 20, n_paths=10_000)
    prob = planner.goal_probability(paths, goal, sc.inflation)
    need = planner.required_contribution(w, sc, goal, 0.7)
    report.planner_report(f"{out}/projection_patrimoniale.pdf", {"nom": "Client exemple"}, prof, w, stats,
                          planner.summarize(paths, sc.inflation), prob, goal, need)
    # 2. Suivi de portefeuille
    hist, label = _history(real)
    target = planner.target_allocation("Équilibré")
    cur_w = pd.Series({"Liquidités": .10, "Obligations souveraines": .10, "Obligations Investment Grade": .20, "Actions Monde": .28,
                       "Actions Europe": .17, "Immobilier coté": .06, "Or": .04, "Private equity": .05})
    if "Private equity" not in hist.columns:       # pas de série réelle : on renormalise sans cette ligne
        cur_w = cur_w.drop("Private equity"); cur_w /= cur_w.sum()
        target = target.drop("Private equity"); target /= target.sum()
    r = portfolio.portfolio_returns(hist[cur_w.index], cur_w)
    bench = portfolio.portfolio_returns(hist[target.index], target)
    values = cur_w * 2_000_000
    report.portfolio_report(f"{out}/suivi_portefeuille.pdf", f"Portefeuille exemple, {label}", r, bench,
                            portfolio.summary(r, bench), portfolio.drift(cur_w, target), portfolio.risk_contribution(hist[cur_w.index], cur_w),
                            portfolio.rebalancing_trades(values, target))
    # 3. Produits structurés
    a = structured.Autocall()
    fc = structured.fair_coupon(a, 98.0, n_paths=20_000)
    a = structured.Autocall(coupon_annuel=fc)
    report.structured_report(f"{out}/produits_structures.pdf", a, structured.price_autocall(a), fc,
                             structured.compare_with_underlying(a), structured.price_capital_protege(structured.CapitalProtege()))
    print(f"Rapports générés dans {out}/")


def run_fetch(refresh: bool, start: str):
    px = market_data.fetch_prices(start=start, refresh=refresh)
    print(f"{px.shape[1]} séries, {px.index[0].date()} → {px.index[-1].date()} (cache : data/prices.csv)")


def run_backtest(out: str = "docs"):
    os.makedirs(out, exist_ok=True)
    r = market_data.monthly_returns(market_data.fetch_prices())
    table = backtest.run(r)
    md = backtest.to_markdown(table, (str(r.index[0].date()), str(r.index[-1].date())), len(r), list(r.columns))
    cal = market_data.calibrate(r)
    blended = market_data.blend_with_priors(cal["table"], data.CMA)
    md += "\n\n## Calibrage des hypothèses de marché\n\n" + \
          f"Historique {cal['periode'][0]} → {cal['periode'][1]} ({cal['n_mois']} mois). Hypothèses retenues = 50 % historique + 50 % a priori de long terme.\n\n" + \
          "| Classe | Rendement hist. | Vol. hist. | Rendement retenu | Vol. retenue |\n|---|---|---|---|---|\n" + \
          "\n".join(f"| {a} | {cal['table'].loc[a,'rendement']*100:.1f} % | {cal['table'].loc[a,'volatilite']*100:.1f} % | "
                    f"{blended.loc[a,'rendement']*100:.1f} % | {blended.loc[a,'volatilite']*100:.1f} % |" for a in cal["table"].index)
    path = f"{out}/backtest_results.md"
    open(path, "w", encoding="utf-8").write(md + "\n")
    print(md)
    print(f"\nÉcrit dans {path}")


def main():
    ap = argparse.ArgumentParser(prog="wealth")
    sub = ap.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("demo", help="génère les 3 rapports PDF d'exemple")
    d.add_argument("--out", default="reports")
    d.add_argument("--real", action="store_true", help="utilise les données réelles téléchargées par `fetch`")
    f = sub.add_parser("fetch", help="télécharge les cours réels (Yahoo Finance) et les met en cache dans data/")
    f.add_argument("--refresh", action="store_true"); f.add_argument("--start", default="2012-01-01")
    b = sub.add_parser("backtest", help="backtest des 4 profils + calibrage sur données réelles")
    b.add_argument("--out", default="docs")
    args = ap.parse_args()
    if args.cmd == "demo":
        run_demo(args.out, args.real)
    elif args.cmd == "fetch":
        run_fetch(args.refresh, args.start)
    elif args.cmd == "backtest":
        run_backtest(args.out)


if __name__ == "__main__":
    main()
