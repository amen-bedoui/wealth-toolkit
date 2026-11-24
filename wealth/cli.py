"""Ligne de commande : python -m wealth demo --out reports"""
from __future__ import annotations
import argparse, os
import pandas as pd
from . import planner, portfolio, structured, report, data


def run_demo(out: str = "reports"):
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
    hist = data.synthetic_history(n_months=60)
    target = planner.target_allocation("Équilibré")
    cur_w = pd.Series({"Liquidités": .10, "Obligations souveraines": .10, "Obligations Investment Grade": .20, "Actions Monde": .28,
                       "Actions Europe": .17, "Immobilier coté": .06, "Or": .04, "Private equity": .05})
    r = portfolio.portfolio_returns(hist, cur_w)
    bench = portfolio.portfolio_returns(hist, target)
    values = cur_w * 2_000_000
    report.portfolio_report(f"{out}/suivi_portefeuille.pdf", "Portefeuille exemple (données simulées)", r, bench,
                            portfolio.summary(r, bench), portfolio.drift(cur_w, target), portfolio.risk_contribution(hist, cur_w),
                            portfolio.rebalancing_trades(values, target))
    # 3. Produits structurés
    a = structured.Autocall()
    fc = structured.fair_coupon(a, 98.0, n_paths=20_000)
    a = structured.Autocall(coupon_annuel=fc)
    report.structured_report(f"{out}/produits_structures.pdf", a, structured.price_autocall(a), fc,
                             structured.compare_with_underlying(a), structured.price_capital_protege(structured.CapitalProtege()))
    print(f"Rapports générés dans {out}/")


def main():
    ap = argparse.ArgumentParser(prog="wealth")
    sub = ap.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("demo", help="génère les 3 rapports PDF d'exemple")
    d.add_argument("--out", default="reports")
    args = ap.parse_args()
    if args.cmd == "demo":
        run_demo(args.out)


if __name__ == "__main__":
    main()
