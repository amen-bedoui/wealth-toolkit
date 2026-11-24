# wealth-toolkit

Boîte à outils Python de **gestion de patrimoine** : planification patrimoniale, suivi de portefeuille privé et analyse de produits structurés, avec rapports PDF prêts à présenter à un client.

Projet personnel d'Amen Bedoui (MSc Banking & International Finance, TBS Education). 25 tests automatisés.

## Ce que fait chaque module

| Module | Question à laquelle il répond | Fonctions clés |
|---|---|---|
| `wealth/planner.py` | « Quelle allocation, et mes objectifs sont-ils atteignables ? » | profil de risque, allocation cible, projection Monte Carlo (versements, retraits, inflation, frais), probabilité d'atteindre un objectif, versement nécessaire |
| `wealth/portfolio.py` | « Comment se comporte le portefeuille, faut-il le rééquilibrer ? » | rendement, volatilité, Sharpe, drawdown, VaR/CVaR, bêta, tracking error, contribution au risque, dérive vs cible, ordres de rééquilibrage avec bande de tolérance |
| `wealth/structured.py` | « Que vaut ce produit structuré et que risque-t-on ? » | autocall à coupons conditionnels avec effet mémoire (Monte Carlo), coupon « juste » pour une marge émetteur donnée, note à capital protégé (zéro-coupon + call Black-Scholes), comparaison produit vs indice en direct |
| `wealth/report.py` | « Comment le présenter au client ? » | 3 rapports PDF |

## Utilisation

```bash
pip install -r requirements.txt
python -m wealth demo --out reports     # génère les 3 rapports PDF
python -m pytest -q                     # 25 tests
```

Exemples de rapports dans `docs/examples/`.

```python
from wealth import planner

profil = planner.risk_profile(horizon_years=15, loss_tolerance=3, experience=2, income_stability=3)
w = planner.target_allocation(profil)
sc = planner.Scenario(patrimoine_initial=500_000, versement_annuel=20_000)
paths = planner.project(w, sc, n_years=20)
planner.goal_probability(paths, planner.Goal("Transmission", 1_000_000, 15))
```

## Méthode

- **Projection** : rendements annuels log-normaux multivariés calibrés sur des hypothèses de long terme (rendement, volatilité, corrélations par classe d'actifs, voir `data.py`), rééquilibrage annuel, frais déduits. Les objectifs sont exprimés en euros d'aujourd'hui.
- **Autocall** : simulation risque-neutre (mouvement brownien géométrique, variables antithétiques) pour la valeur du produit ; simulation en monde réel (drift configurable) pour comparer le TRI du produit à celui de l'indice.
- **Capital protégé** : valeur du zéro-coupon + budget d'option ; la participation à la hausse est le budget divisé par le prix du call ATM.

## Ce que montre la démo (à titre d'illustration)

- Un autocall dont le coupon est calé pour laisser 2 % de marge à l'émetteur affiche environ 16 % de probabilité de perte en capital sur 8 ans et un TRI moyen inférieur à l'indice, mais avec un scénario défavorable bien meilleur (−0,4 % contre −4,9 % pour les 5 % pires cas). Le produit vend du potentiel de hausse contre de la régularité.
- La projection d'un portefeuille « Dynamique » (500 k€ + 20 k€/an) donne environ 58 % de chances d'atteindre 1 M€ en euros d'aujourd'hui à 15 ans.

## Limites (volontairement explicites)

- **Données simulées** : l'historique du suivi de portefeuille est généré (graine fixe), pas des cours réels. Les hypothèses de marché sont illustratives, pas des prévisions.
- Pas de fiscalité, pas de risque de crédit de l'émetteur, pas de liquidité de marché secondaire, pas de coûts de transaction dans les rééquilibrages.
- Le TRI produit/indice de `compare_with_underlying` est approximé (coupons non réinvestis).
- Volatilité constante (Black-Scholes) : pas de smile ni de volatilité stochastique.
- Outil pédagogique : ne constitue pas un conseil en investissement.

## Pistes d'évolution

Données réelles (import CSV de cours), fiscalité (assurance-vie, PEA), volatilité locale pour les produits structurés, optimisation d'allocation sous contraintes.
