# Fibo – Scanner 200 WMA & Portefeuille

Application Streamlit (données Yahoo Finance via `yfinance`, cours hebdomadaires sur 10 ans, cache 24 h).

- **Scanner** : CAC 40 / Nasdaq 100 / S&P 500, moyenne mobile 200 semaines, signal ACHAT si cours ≤ 200 WMA × 1,05.
- **Portefeuille** : ZigZag (seuil réglable, 20 % par défaut), points A/B/C,
  objectif = C + 2,618 × (B − A), signal VENTE si cours ≥ objectif × 0,97.

Lancer en local :

```bash
pip install -r requirements.txt
streamlit run app.py
```
