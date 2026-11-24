# Fibo – Opportunités

Application Streamlit (données Yahoo Finance, cours hebdomadaires sur 10 ans, cache 24 h).

Un seul écran :
1. **Choix de l'indice** : CAC 40, Nasdaq 100, S&P 500.
2. **Tableau** avec deux notes sur 10 pour chaque action :
   - **Note technique** : position et tendance de la 200 WMA, retracement de Fibonacci, RSI hebdomadaire, rebond.
   - **Note fondamentale** : évolution du chiffre d'affaires, rentabilité (ROE), free cash flow, dette nette / EBITDA, PER au cours actuel vs son historique.
3. **Fiche action** (liste déroulante) : détail des critères, seuils d'achat 1-2-3, stop, graphiques.

Lancer en local :

```bash
pip install -r requirements.txt
streamlit run app.py
```

⚠️ Outil d'aide à la réflexion, pas un conseil en investissement.
