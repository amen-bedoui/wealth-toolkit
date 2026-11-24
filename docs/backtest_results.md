Backtest des 4 profils sur **2012-02-29 → 2026-11-30** (178 mois), rééquilibrage mensuel, sans frais ni fiscalité. Classes utilisées : Liquidités, Obligations souveraines, Obligations Investment Grade, Actions Monde, Actions Europe, Immobilier coté, Or.

| Profil | Rendement annualisé | Volatilité | Sharpe | Drawdown max | Pire année |
|---|---|---|---|---|---|
| Prudent | 3.4 % | 5.0 % | 0.27 | -15.1 % | -14.2 % (2022) |
| Équilibré | 5.7 % | 7.0 % | 0.53 | -16.2 % | -14.3 % (2022) |
| Dynamique | 7.6 % | 8.8 % | 0.63 | -16.9 % | -14.5 % (2022) |
| Offensif | 9.1 % | 10.5 % | 0.68 | -18.0 % | -14.8 % (2022) |

Les performances passées ne préjugent pas des performances futures.

## Calibrage des hypothèses de marché

Historique 2012-02-29 → 2026-11-30 (178 mois). Hypothèses retenues = 50 % historique + 50 % a priori de long terme (rendements, volatilités et corrélations). Elles sont enregistrées dans data/calibration.json et utilisées automatiquement par `demo --real` et par l'application.

| Classe | Rendement hist. | Vol. hist. | Rendement retenu | Vol. retenue |
|---|---|---|---|---|
| Liquidités | 0.5 % | 0.4 % | 1.5 % | 0.5 % |
| Obligations souveraines | 1.4 % | 5.1 % | 2.2 % | 5.6 % |
| Obligations Investment Grade | 1.8 % | 4.4 % | 2.9 % | 5.5 % |
| Actions Monde | 12.6 % | 12.4 % | 9.8 % | 13.9 % |
| Actions Europe | 9.2 % | 13.0 % | 8.1 % | 15.0 % |
| Immobilier coté | 3.9 % | 18.0 % | 4.9 % | 17.0 % |
| Or | 4.8 % | 16.2 % | 4.1 % | 15.6 % |
