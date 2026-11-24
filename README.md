# wealth-toolkit

[![tests](../../actions/workflows/tests.yml/badge.svg)](../../actions/workflows/tests.yml)

Boîte à outils Python de **gestion de patrimoine** : planification patrimoniale, suivi de portefeuille privé, produits structurés et fiscalité France / Monaco, avec une application web et des rapports PDF prêts à présenter à un client.

Projet personnel d'Amen Bedoui (MSc Banking & International Finance, TBS Education). 63 tests automatisés.

## Contenu

| Module | Question à laquelle il répond | Fonctions clés |
|---|---|---|
| `planner.py` | Quelle allocation, et mes objectifs sont-ils atteignables ? | profil de risque, allocation cible, projection Monte Carlo (versements, retraits, inflation, frais), probabilité d'atteinte d'un objectif, versement nécessaire |
| `portfolio.py` | Comment se comporte le portefeuille, faut-il rééquilibrer ? | rendement, volatilité, Sharpe, drawdown, VaR/CVaR, bêta, tracking error, contribution au risque, dérive vs cible, ordres de rééquilibrage avec bande de tolérance |
| `market_data.py` | Et sur de vraies données ? | téléchargement Yahoo Finance avec cache CSV, import CSV client (format français accepté), calibrage historique, rétrécissement vers des a priori de long terme |
| `backtest.py` | Comment les 4 profils auraient-ils évolué ? | rendement, volatilité, Sharpe, drawdown maximal, pire année civile complète |
| `tax.py` | Combien reste-t-il après impôt, et à la transmission ? | CTO, PEA, assurance-vie, résident monégasque ; droits de succession et donation France / Monaco ; paramètres datés et sourcés dans `tax_params.json` |
| `structured.py` | Que vaut ce produit structuré et que risque-t-on ? | autocall et Phoenix (coupon conditionnel, mémoire), reverse convertible à barrière, capital protégé, coupon « juste » pour une marge d'émetteur donnée, comparaison produit vs indice |
| `report.py` | Comment le présenter au client ? | 3 rapports PDF |
| `app.py` | Interface | application Streamlit à 4 onglets, export PDF |

## Installation et usage

```bash
pip install -e ".[dev]"
python -m pytest -q                 # 63 tests, sans accès réseau

wealth fetch                        # télécharge les cours réels (Yahoo Finance) dans data/
wealth backtest                     # backtest des profils + calibrage -> docs/backtest_results.md
wealth demo --real                  # 3 rapports PDF sur données réelles (sans --real : données simulées, étiquetées)
streamlit run app.py                # application web
```

```python
from wealth import planner, tax

w = planner.target_allocation(planner.risk_profile(15, 3, 2, 3))
paths = planner.project(w, planner.Scenario(500_000, 20_000), n_years=20)
planner.goal_probability(paths, planner.Goal("Transmission", 1_000_000, 15))
tax.inheritance_tax(500_000, "ligne_directe", residence="France")["droits"]
```

## Aperçu

| Projection patrimoniale | Suivi de portefeuille | Produits structurés |
|---|---|---|
| ![](docs/img/projection_patrimoniale-1.png) | ![](docs/img/suivi_portefeuille-1.png) | ![](docs/img/produits_structures-1.png) |

Les PDF complets sont dans `docs/examples/` (générés avec des données **simulées** : voir la section suivante).

## Données : ce qui est réel, ce qui est simulé

- **Réel** : `wealth fetch` télécharge des ETF cotés représentatifs de chaque classe d'actifs (liste modifiable dans `market_data.DEFAULT_TICKERS`). Le backtest et le calibrage tournent dessus.
- **Simulé** : sans cache de données réelles, la démo et l'onglet « Suivi de portefeuille » utilisent un historique généré (graine fixe) et l'indiquent. Les PDF d'exemple fournis dans `docs/examples/` ont été produits ainsi, car leur génération s'est faite sans accès à Yahoo Finance.
- **Hypothèses** : rendements, volatilités et corrélations de `data.py` sont des ordres de grandeur de long terme, pas des prévisions. Le private equity n'a pas de série de prix gratuite : il garde son hypothèse manuelle.
- **Résultats du backtest** : ils ne sont pas recopiés ici à la main. Lance `wealth fetch && wealth backtest` : le tableau (et le calibrage retenu) est écrit dans `docs/backtest_results.md` à partir des données téléchargées.

## Méthode

- **Projection** : rendements annuels log-normaux multivariés, rééquilibrage annuel, frais déduits ; objectifs exprimés en euros d'aujourd'hui.
- **Fiscalité** : appliquée à la liquidation totale à l'horizon. Taux 2026 : flat tax 12,8 % d'impôt + 18,6 % de prélèvements sociaux (CSG relevée par la LFSS 2026), assurance-vie à 17,2 % de prélèvements sociaux, abattement de 4 600 € / 9 200 € après 8 ans, 7,5 % sur les produits liés aux primes inférieures à 150 000 €. Droits de succession en ligne directe : abattement de 100 000 € puis barème de 5 % à 45 %. Sources officielles dans `wealth/tax_params.json` (service-public.gouv.fr, impots.gouv.fr). **Barèmes validés au 24/11/2026** : à revalider à chaque loi de finances.
- **Produits structurés** : simulation risque-neutre (mouvement brownien géométrique, variables antithétiques) pour la valeur ; simulation en monde réel pour comparer le rendement du produit à celui de l'indice.

## Limites connues

- Fiscalité simplifiée : un seul contribuable, flat tax (pas de barème progressif de l'IR), pas de fiscalité au fil de l'eau, abattement d'assurance-vie utilisé une seule fois. Le cas d'un Français résidant à Monaco (imposé en France) n'est pas modélisé. Les paramètres monégasques sont une hypothèse à faire valider.
- Produits structurés : volatilité constante, pas de smile, pas de risque de crédit de l'émetteur ni de liquidité secondaire. Le TRI produit/indice est approximé (coupons non réinvestis).
- Le rendement passé est un mauvais estimateur du rendement futur : le calibrage est combiné à 50 % avec des a priori de long terme.
- Pas de coûts de transaction dans les rééquilibrages.
- Outil pédagogique : ne constitue pas un conseil en investissement ni fiscal.
