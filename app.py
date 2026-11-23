# -*- coding: utf-8 -*-
"""
Application Streamlit : Scanner 200 WMA + Portefeuille avec objectifs Fibonacci.

Écran 1 "Scanner"      : repère les actions proches de leur moyenne mobile 200 semaines.
Écran 2 "Portefeuille" : calcule un objectif de vente avec un ZigZag + extension 2,618.

Lancer en local :  streamlit run app.py
"""

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from io import StringIO

import pandas as pd
import plotly.graph_objects as go
import requests
import streamlit as st
import yfinance as yf

# ---------------------------------------------------------------------------
# Configuration générale de la page
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="Scanner 200 WMA & Portefeuille",
    page_icon="📈",
    layout="wide",  # utilise toute la largeur (s'adapte aussi à l'écran d'un iPhone)
)

# Durée du cache : 24 heures (en secondes). Les données ne sont retéléchargées qu'une fois par jour.
CACHE_24H = 24 * 60 * 60

# Nombre de semaines pour la moyenne mobile
PERIODE_WMA = 200

# En-tête "navigateur" pour que Wikipédia accepte nos requêtes
ENTETES_HTTP = {"User-Agent": "Mozilla/5.0 (compatible; scanner-streamlit/1.0)"}

# ---------------------------------------------------------------------------
# Listes des indices
# ---------------------------------------------------------------------------

# CAC 40 : liste écrite "en dur" (la composition change rarement).
# Si un titre entre ou sort de l'indice, il suffit de modifier cette liste.
CAC40 = {
    "AC.PA": "Accor",
    "AI.PA": "Air Liquide",
    "AIR.PA": "Airbus",
    "MT.PA": "ArcelorMittal",
    "CS.PA": "AXA",
    "BNP.PA": "BNP Paribas",
    "EN.PA": "Bouygues",
    "BVI.PA": "Bureau Veritas",
    "CAP.PA": "Capgemini",
    "CA.PA": "Carrefour",
    "ACA.PA": "Crédit Agricole",
    "BN.PA": "Danone",
    "DSY.PA": "Dassault Systèmes",
    "EDEN.PA": "Edenred",
    "ENGI.PA": "Engie",
    "EL.PA": "EssilorLuxottica",
    "ERF.PA": "Eurofins Scientific",
    "ENX.PA": "Euronext",
    "RMS.PA": "Hermès",
    "KER.PA": "Kering",
    "OR.PA": "L'Oréal",
    "LR.PA": "Legrand",
    "MC.PA": "LVMH",
    "ML.PA": "Michelin",
    "ORA.PA": "Orange",
    "RI.PA": "Pernod Ricard",
    "PUB.PA": "Publicis",
    "RNO.PA": "Renault",
    "SAF.PA": "Safran",
    "SGO.PA": "Saint-Gobain",
    "SAN.PA": "Sanofi",
    "SU.PA": "Schneider Electric",
    "GLE.PA": "Société Générale",
    "STLAP.PA": "Stellantis",
    "STMPA.PA": "STMicroelectronics",
    "HO.PA": "Thales",
    "TTE.PA": "TotalEnergies",
    "URW.PA": "Unibail-Rodamco-Westfield",
    "VIE.PA": "Veolia",
    "DG.PA": "Vinci",
}

# Liste de secours pour le Nasdaq 100 (utilisée seulement si Wikipédia est inaccessible).
NASDAQ100_SECOURS = [
    "AAPL", "ABNB", "ADBE", "ADI", "ADP", "ADSK", "AEP", "AMAT", "AMD", "AMGN",
    "AMZN", "ANSS", "APP", "ARM", "ASML", "AVGO", "AXON", "AZN", "BIIB", "BKNG",
    "BKR", "CCEP", "CDNS", "CDW", "CEG", "CHTR", "CMCSA", "COST", "CPRT", "CRWD",
    "CSCO", "CSGP", "CSX", "CTAS", "CTSH", "DASH", "DDOG", "DXCM", "EA", "EXC",
    "FANG", "FAST", "FTNT", "GEHC", "GFS", "GILD", "GOOG", "GOOGL", "HON", "IDXX",
    "INTC", "INTU", "ISRG", "KDP", "KHC", "KLAC", "LIN", "LRCX", "LULU", "MAR",
    "MCHP", "MDB", "MDLZ", "MELI", "META", "MNST", "MRVL", "MSFT", "MSTR", "MU",
    "NFLX", "NVDA", "NXPI", "ODFL", "ON", "ORLY", "PANW", "PAYX", "PCAR", "PDD",
    "PEP", "PLTR", "PYPL", "QCOM", "REGN", "ROP", "ROST", "SBUX", "SNPS", "TEAM",
    "TMUS", "TSLA", "TTD", "TTWO", "TXN", "VRSK", "VRTX", "WBD", "WDAY", "XEL",
    "ZS",
]


def tableau_wikipedia(url, colonne_ticker, colonne_nom):
    """Lit le tableau des composants d'un indice sur Wikipédia.

    Renvoie un dictionnaire {ticker: nom}.
    """
    reponse = requests.get(url, headers=ENTETES_HTTP, timeout=20)
    reponse.raise_for_status()
    # pandas sait lire tous les tableaux HTML d'une page
    tableaux = pd.read_html(StringIO(reponse.text))
    for tableau in tableaux:
        if colonne_ticker in tableau.columns and colonne_nom in tableau.columns:
            resultat = {}
            for _, ligne in tableau.iterrows():
                # Yahoo Finance écrit "BRK-B" et non "BRK.B"
                ticker = str(ligne[colonne_ticker]).strip().replace(".", "-")
                resultat[ticker] = str(ligne[colonne_nom]).strip()
            if len(resultat) > 50:  # on vérifie que c'est bien le bon tableau
                return resultat
    raise ValueError("Tableau des composants introuvable")


@st.cache_data(ttl=CACHE_24H, show_spinner=False)
def liste_nasdaq100():
    """Composants du Nasdaq 100 (Wikipédia, sinon liste de secours)."""
    try:
        return tableau_wikipedia(
            "https://en.wikipedia.org/wiki/Nasdaq-100", "Ticker", "Company"
        )
    except Exception:
        return {t: t for t in NASDAQ100_SECOURS}


@st.cache_data(ttl=CACHE_24H, show_spinner=False)
def liste_sp500():
    """Composants du S&P 500 (Wikipédia, sinon un fichier CSV public sur GitHub)."""
    try:
        return tableau_wikipedia(
            "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies",
            "Symbol",
            "Security",
        )
    except Exception:
        url_csv = (
            "https://raw.githubusercontent.com/datasets/"
            "s-and-p-500-companies/main/data/constituents.csv"
        )
        reponse = requests.get(url_csv, headers=ENTETES_HTTP, timeout=20)
        df = pd.read_csv(StringIO(reponse.text))
        return {
            str(s).replace(".", "-"): str(n)
            for s, n in zip(df["Symbol"], df["Security"])
        }


def composants_indice(nom_indice):
    """Renvoie {ticker: nom} pour l'indice choisi."""
    if nom_indice == "CAC 40":
        return CAC40
    if nom_indice == "Nasdaq 100":
        return liste_nasdaq100()
    return liste_sp500()


# ---------------------------------------------------------------------------
# Téléchargement des cours (yfinance)
# ---------------------------------------------------------------------------


@st.cache_data(ttl=CACHE_24H, show_spinner=False)
def cours_hebdo(tickers):
    """Télécharge les cours de clôture HEBDOMADAIRES sur 10 ans.

    `tickers` est un tuple (et non une liste) pour que le cache fonctionne.
    Renvoie un tableau : une ligne par semaine, une colonne par ticker.
    """
    morceaux = []
    tickers = list(tickers)
    # On télécharge par paquets de 100 pour ne pas surcharger Yahoo Finance
    for debut in range(0, len(tickers), 100):
        paquet = tickers[debut : debut + 100]
        donnees = yf.download(
            paquet,
            period="10y",
            interval="1wk",
            auto_adjust=True,  # cours ajustés des dividendes et divisions
            progress=False,
            threads=True,
        )
        if donnees is None or donnees.empty:
            continue
        clotures = donnees["Close"]
        # Avec un seul ticker, yfinance peut renvoyer une simple colonne
        if isinstance(clotures, pd.Series):
            clotures = clotures.to_frame(name=paquet[0])
        morceaux.append(clotures)

    if not morceaux:
        return pd.DataFrame()
    resultat = pd.concat(morceaux, axis=1)
    resultat = resultat.loc[:, ~resultat.columns.duplicated()]
    return resultat.sort_index()


def serie_cours(ticker):
    """Cours hebdomadaires d'un seul ticker (Series sans valeurs vides)."""
    df = cours_hebdo((ticker,))
    if df.empty or ticker not in df.columns:
        return pd.Series(dtype=float)
    return df[ticker].dropna()


# ---------------------------------------------------------------------------
# Calculs : ZigZag et objectif Fibonacci
# ---------------------------------------------------------------------------


def zigzag(serie, seuil):
    """Détecte les sommets et les creux avec un ZigZag en pourcentage.

    - `serie` : cours de clôture (pandas Series indexée par date)
    - `seuil` : variation minimale, ex. 0.20 pour 20 %

    Un sommet est "confirmé" quand le cours a ensuite baissé d'au moins `seuil`,
    un creux est confirmé quand le cours a ensuite monté d'au moins `seuil`.

    Renvoie (pivots_confirmes, dernier_pivot_provisoire)
    où chaque pivot est un dict {date, prix, type} avec type = "creux" ou "sommet".
    """
    valeurs = serie.values
    dates = serie.index
    if len(valeurs) < 2:
        return [], None

    pivots = []
    tendance = None  # "hausse", "baisse" ou None (pas encore déterminée)
    i_haut = i_bas = 0  # plus haut / plus bas depuis le début (avant la 1re tendance)
    i_extreme = 0  # point extrême de la tendance en cours

    for i in range(1, len(valeurs)):
        v = valeurs[i]

        if tendance is None:
            # Phase de démarrage : on attend un premier mouvement >= seuil
            if v > valeurs[i_haut]:
                i_haut = i
            if v < valeurs[i_bas]:
                i_bas = i
            if v >= valeurs[i_bas] * (1 + seuil):
                pivots.append({"date": dates[i_bas], "prix": valeurs[i_bas], "type": "creux"})
                tendance, i_extreme = "hausse", i
            elif v <= valeurs[i_haut] * (1 - seuil):
                pivots.append({"date": dates[i_haut], "prix": valeurs[i_haut], "type": "sommet"})
                tendance, i_extreme = "baisse", i

        elif tendance == "hausse":
            if v > valeurs[i_extreme]:
                i_extreme = i  # nouveau plus haut : le sommet se déplace
            elif v <= valeurs[i_extreme] * (1 - seuil):
                # Baisse suffisante : le sommet est confirmé
                pivots.append({"date": dates[i_extreme], "prix": valeurs[i_extreme], "type": "sommet"})
                tendance, i_extreme = "baisse", i

        else:  # tendance == "baisse"
            if v < valeurs[i_extreme]:
                i_extreme = i  # nouveau plus bas : le creux se déplace
            elif v >= valeurs[i_extreme] * (1 + seuil):
                # Hausse suffisante : le creux est confirmé
                pivots.append({"date": dates[i_extreme], "prix": valeurs[i_extreme], "type": "creux"})
                tendance, i_extreme = "hausse", i

    provisoire = None
    if tendance is not None:
        provisoire = {
            "date": dates[i_extreme],
            "prix": valeurs[i_extreme],
            "type": "sommet" if tendance == "hausse" else "creux",
        }
    return pivots, provisoire


def points_abc(pivots):
    """Trouve la dernière séquence creux A -> sommet B -> creux C (pivots confirmés).

    Renvoie (A, B, C) ou None si le ZigZag n'a pas encore assez de points.
    """
    for k in range(len(pivots) - 1, 1, -1):
        a, b, c = pivots[k - 2], pivots[k - 1], pivots[k]
        if a["type"] == "creux" and b["type"] == "sommet" and c["type"] == "creux":
            return a, b, c
    return None


def objectif_vente(a, b, c):
    """Objectif de vente = C + 2,618 x (B - A)."""
    return c["prix"] + 2.618 * (b["prix"] - a["prix"])


# ---------------------------------------------------------------------------
# Score qualité (analyse fondamentale)
# ---------------------------------------------------------------------------
# 5 critères, 1 point chacun :
#   1. Croissance du chiffre d'affaires   2. Rentabilité (ROE et marge)
#   3. Free cash flow positif             4. Endettement raisonnable
#   5. PER actuel inférieur ou égal à son PER moyen des années précédentes
# Un critère sans données (ou non applicable, ex. la dette pour une banque)
# n'est pas compté : le score s'affiche alors sur 4 ou sur 3.
#
# Toutes les données viennent des comptes annuels publiés (environ 4 ans),
# téléchargés UNIQUEMENT pour les actions ayant un signal ACHAT, doucement
# (3 à la fois) pour ne pas être bloqué par Yahoo Finance.

# Seuils des critères (modifiables)
CROISSANCE_CA_MIN = 0.05  # croissance annuelle moyenne du CA : 5 %
ROE_MIN = 0.12  # rentabilité des capitaux propres : 12 %
DETTE_EBITDA_MAX = 2.5  # dette nette / EBITDA

# Banques et assurances du CAC 40 (pour elles, dette et free cash flow ne veulent rien dire)
FINANCIERES_CAC40 = {"BNP.PA", "ACA.PA", "GLE.PA", "CS.PA"}


@st.cache_data(ttl=CACHE_24H, show_spinner=False)
def financieres_us(nom_indice):
    """Liste des tickers du secteur financier (Nasdaq 100 / S&P 500), lue sur Wikipédia."""
    sources = {
        "Nasdaq 100": ("https://en.wikipedia.org/wiki/Nasdaq-100", "Ticker"),
        "S&P 500": ("https://en.wikipedia.org/wiki/List_of_S%26P_500_companies", "Symbol"),
    }
    url, colonne_ticker = sources[nom_indice]
    try:
        reponse = requests.get(url, headers=ENTETES_HTTP, timeout=20)
        for tableau in pd.read_html(StringIO(reponse.text)):
            colonnes_secteur = [c for c in tableau.columns if "Sector" in str(c) or "Industry" in str(c)]
            if colonne_ticker in tableau.columns and colonnes_secteur and len(tableau) > 50:
                secteur = tableau[colonnes_secteur[0]].astype(str)
                tickers = tableau[colonne_ticker].astype(str).str.replace(".", "-", regex=False)
                return set(tickers[secteur.str.contains("Financ")])
    except Exception:
        pass
    return set()


def est_financiere(ticker, nom_indice):
    if nom_indice == "CAC 40":
        return ticker in FINANCIERES_CAC40
    return ticker in financieres_us(nom_indice)


def _serie_comptable(tableau, noms):
    """Extrait une ligne d'un état financier : Series {date de clôture: valeur}, de la plus ancienne à la plus récente."""
    if tableau is None or tableau.empty:
        return pd.Series(dtype=float)
    for nom in noms:
        if nom in tableau.index:
            return pd.to_numeric(tableau.loc[nom], errors="coerce").dropna().sort_index()
    return pd.Series(dtype=float)


def _valeurs(serie):
    return [float(v) for v in serie.values]


def _telecharger_comptes(ticker):
    """Télécharge les comptes annuels d'une action, avec 3 tentatives.

    Renvoie (donnees, None) si tout va bien, ou (None, message_d_erreur).
    """
    erreur = "réponse vide de Yahoo Finance"
    for tentative in range(3):
        try:
            action = yf.Ticker(ticker)
            compte = action.income_stmt
            if compte is None or compte.empty:
                raise ValueError("compte de résultat vide (Yahoo limite peut-être les requêtes)")
            bilan = action.balance_sheet
            flux = action.cashflow
            bpa = _serie_comptable(compte, ["Diluted EPS", "Basic EPS"])
            donnees = {
                "ca": _valeurs(_serie_comptable(compte, ["Total Revenue", "Operating Revenue"])),
                "resultat_op": _valeurs(_serie_comptable(compte, ["Operating Income"])),
                "resultat_net": _valeurs(_serie_comptable(compte, ["Net Income", "Net Income Common Stockholders"])),
                "ebitda": _valeurs(_serie_comptable(compte, ["EBITDA", "Normalized EBITDA"])),
                "bpa": {str(d.date()): float(v) for d, v in bpa.items()},  # bénéfice par action par année
                "capitaux_propres": _valeurs(_serie_comptable(bilan, ["Stockholders Equity", "Common Stock Equity"])),
                "dette": _valeurs(_serie_comptable(bilan, ["Total Debt"])),
                "tresorerie": _valeurs(_serie_comptable(
                    bilan, ["Cash Cash Equivalents And Short Term Investments", "Cash And Cash Equivalents"])),
                "fcf": _valeurs(_serie_comptable(flux, ["Free Cash Flow"])),
            }
            return donnees, None
        except Exception as e:
            erreur = str(e) or e.__class__.__name__
            time.sleep(2 + 3 * tentative)  # on patiente un peu plus à chaque essai
    return None, erreur


@st.cache_resource(show_spinner=False)
def _memoire_comptes():
    """Mémoire partagée {ticker: (heure, données)} : on n'y garde QUE les réussites."""
    return {}


def comptes_annuels(tickers):
    """Comptes des actions demandées. Renvoie (resultats, erreurs).

    Les réussites sont gardées 24 h ; les échecs seront retentés au prochain affichage.
    """
    memoire = _memoire_comptes()
    maintenant = time.time()
    resultats, erreurs = {}, {}
    a_telecharger = []
    for t in tickers:
        if t in memoire and maintenant - memoire[t][0] < CACHE_24H:
            resultats[t] = memoire[t][1]
        else:
            a_telecharger.append(t)

    if a_telecharger:
        barre = st.progress(0.0, text="Téléchargement des comptes annuels…")
        # 3 téléchargements à la fois seulement, pour ne pas être bloqué par Yahoo
        with ThreadPoolExecutor(max_workers=3) as executeur:
            taches = {executeur.submit(_telecharger_comptes, t): t for t in a_telecharger}
            for n, tache in enumerate(as_completed(taches), start=1):
                t = taches[tache]
                donnees, erreur = tache.result()
                if donnees is not None:
                    memoire[t] = (time.time(), donnees)
                    resultats[t] = donnees
                else:
                    erreurs[t] = erreur
                barre.progress(n / len(a_telecharger), text=f"Comptes annuels : {n}/{len(a_telecharger)}")
        barre.empty()
    return resultats, erreurs


def score_qualite(comptes, cours, financiere):
    """Évalue les 5 critères. Renvoie (points, nb_criteres_evalues, liste_des_criteres).

    Chaque critère est un dict : nom, ok (True / False / None si non évaluable), détail.
    """
    criteres = []

    # 1. Croissance du chiffre d'affaires
    ca = comptes["ca"][-4:]
    if len(ca) >= 2 and ca[0] > 0:
        annees = len(ca) - 1
        croissance_moy = (ca[-1] / ca[0]) ** (1 / annees) - 1
        derniere = ca[-1] / ca[-2] - 1
        criteres.append({
            "nom": "Croissance du chiffre d'affaires",
            "ok": croissance_moy > CROISSANCE_CA_MIN and derniere >= 0,
            "detail": f"{croissance_moy:+.1%} par an sur {annees} an(s), dernière année {derniere:+.1%} "
                      f"(il faut > {CROISSANCE_CA_MIN:.0%} par an et pas de recul)",
        })
    else:
        criteres.append({"nom": "Croissance du chiffre d'affaires", "ok": None, "detail": "Données absentes"})

    # 2. Rentabilité : ROE = résultat net / capitaux propres, et marge opérationnelle stable
    net, cp = comptes["resultat_net"], comptes["capitaux_propres"]
    if net and cp and cp[-1] > 0:
        roe = net[-1] / cp[-1]
        ok = roe >= ROE_MIN
        detail = f"ROE {roe:.1%} (il faut ≥ {ROE_MIN:.0%})"
        res_op, tout_ca = comptes["resultat_op"], comptes["ca"]
        if not financiere and len(res_op) >= 2 and len(tout_ca) >= 2 and tout_ca[-1] and tout_ca[-2]:
            marges = [res_op[-2] / tout_ca[-2], res_op[-1] / tout_ca[-1]]
            ok = ok and marges[1] >= marges[0] - 0.01  # tolérance d'un point
            detail += f", marge opérationnelle {marges[0]:.1%} → {marges[1]:.1%} (ne doit pas baisser)"
        criteres.append({"nom": "Rentabilité", "ok": ok, "detail": detail})
    elif net and cp and cp[-1] <= 0:
        criteres.append({"nom": "Rentabilité", "ok": False, "detail": "Capitaux propres négatifs"})
    else:
        criteres.append({"nom": "Rentabilité", "ok": None, "detail": "Données absentes"})

    # 3. Free cash flow positif sur les 2 dernières années
    fcf = comptes["fcf"][-2:]
    if financiere:
        criteres.append({"nom": "Free cash flow", "ok": None, "detail": "Non applicable (banque / assurance)"})
    elif fcf:
        texte = ", ".join(f"{v / 1e9:+.2f} Md" for v in fcf)
        criteres.append({"nom": "Free cash flow", "ok": all(v > 0 for v in fcf),
                         "detail": f"{texte} (doit être positif)"})
    else:
        criteres.append({"nom": "Free cash flow", "ok": None, "detail": "Données absentes"})

    # 4. Endettement : dette nette / EBITDA
    dette, treso, ebitda = comptes["dette"], comptes["tresorerie"], comptes["ebitda"]
    if financiere:
        criteres.append({"nom": "Endettement", "ok": None, "detail": "Non applicable (banque / assurance)"})
    elif dette or treso:
        dette_nette = (dette[-1] if dette else 0) - (treso[-1] if treso else 0)
        if dette_nette <= 0:
            criteres.append({"nom": "Endettement", "ok": True, "detail": "Plus de trésorerie que de dettes"})
        elif ebitda and ebitda[-1] > 0:
            ratio = dette_nette / ebitda[-1]
            criteres.append({"nom": "Endettement", "ok": ratio < DETTE_EBITDA_MAX,
                             "detail": f"Dette nette / EBITDA = {ratio:.1f} (il faut < {DETTE_EBITDA_MAX})"})
        elif ebitda:
            criteres.append({"nom": "Endettement", "ok": False, "detail": "Endettée avec un EBITDA négatif"})
        else:
            criteres.append({"nom": "Endettement", "ok": None, "detail": "EBITDA absent"})
    else:
        criteres.append({"nom": "Endettement", "ok": None, "detail": "Données absentes"})

    # 5. PER actuel vs PER moyen des années précédentes
    #    PER d'une année = cours à la date de clôture des comptes / bénéfice par action de l'année
    bpa = pd.Series(comptes["bpa"], dtype=float)
    bpa.index = pd.to_datetime(bpa.index)
    bpa = bpa.sort_index()
    if bpa.empty or cours.empty:
        criteres.append({"nom": "PER vs son historique", "ok": None, "detail": "Données absentes"})
    elif bpa.iloc[-1] <= 0:
        criteres.append({"nom": "PER vs son historique", "ok": False, "detail": "L'entreprise perd de l'argent"})
    else:
        per_actuel = cours.iloc[-1] / bpa.iloc[-1]
        per_passes = []
        for date, b in bpa.iloc[:-1].items():
            prix = cours.asof(date)  # cours de la semaine de clôture des comptes
            if b > 0 and pd.notna(prix):
                per_passes.append(prix / b)
        if len(per_passes) >= 2:
            moyenne = sum(per_passes) / len(per_passes)
            criteres.append({"nom": "PER vs son historique", "ok": per_actuel <= moyenne,
                             "detail": f"PER actuel {per_actuel:.1f} contre {moyenne:.1f} en moyenne "
                                       f"les {len(per_passes)} années précédentes (doit être ≤)"})
        else:
            criteres.append({"nom": "PER vs son historique", "ok": None, "detail": "Historique trop court"})

    evalues = [c for c in criteres if c["ok"] is not None]
    points = sum(1 for c in evalues if c["ok"])
    return points, len(evalues), criteres


def verdict(points, evalues):
    """Transforme le score en verdict lisible."""
    if evalues < 3:
        return "⚪ Données insuffisantes"
    ratio = points / evalues
    if ratio >= 0.8:
        return "🟢 ACHAT"
    if ratio >= 0.4:
        return "🟡 À surveiller"
    return "🔴 Piège possible"


def section_qualite(nom_indice, cours, tableau):
    """Affiche le score qualité des actions ayant un signal ACHAT technique."""
    st.subheader("🏅 Score qualité")
    st.caption(
        "Vérifie la santé de l'entreprise pour éviter les « pièges » : croissance du CA, "
        "rentabilité, free cash flow, dette, PER par rapport à son historique."
    )
    candidats = tableau[tableau["Signal"] != ""]
    if candidats.empty:
        st.info("Aucun signal ACHAT technique à analyser.")
        return
    if not st.toggle(f"Calculer le score qualité des {len(candidats)} signaux ACHAT", key=f"qualite_{nom_indice}"):
        st.caption("Le premier calcul peut prendre quelques minutes (puis il est gardé 24 h).")
        return

    comptes, erreurs = comptes_annuels(list(candidats["Ticker"]))

    if erreurs:
        st.warning(
            f"Données indisponibles pour {len(erreurs)} action(s) sur {len(candidats)}. "
            "Yahoo Finance limite sans doute le nombre de requêtes : patientez quelques minutes "
            "puis appuyez sur « Réessayer »."
        )
        if st.button("🔄 Réessayer", key=f"reessayer_{nom_indice}"):
            st.rerun()
        with st.expander("Détails techniques"):
            for t, e in erreurs.items():
                st.text(f"{t} : {e}")

    lignes, fiches = [], {}
    for _, ligne in candidats.iterrows():
        t = ligne["Ticker"]
        if t not in comptes:
            continue
        points, evalues, criteres = score_qualite(
            comptes[t], cours[t].dropna(), est_financiere(t, nom_indice)
        )
        fiches[t] = (ligne["Nom"], points, evalues, criteres)
        lignes.append({
            "Ticker": t,
            "Nom": ligne["Nom"],
            "Écart %": ligne["Écart %"],
            "Qualité": f"{points}/{evalues}",
            "Verdict": verdict(points, evalues),
            "_tri": points / evalues if evalues >= 3 else -1,  # données insuffisantes en bas
        })

    if not lignes:
        return

    resultat = pd.DataFrame(lignes).sort_values(["_tri", "Écart %"], ascending=[False, True])
    st.dataframe(
        resultat.drop(columns="_tri"),
        hide_index=True,
        width="stretch",
        column_config={"Écart %": st.column_config.NumberColumn(format="%+.1f %%")},
    )
    st.caption("🟢 ≥ 80 % des critères · 🟡 40 à 79 % · 🔴 < 40 % · ⚪ moins de 3 critères évaluables")

    # Fiche détaillée : explique chaque critère
    choix = st.selectbox(
        "Fiche détaillée", resultat["Ticker"],
        format_func=lambda t: f"{t} — {fiches[t][0]}",
    )
    nom, points, evalues, criteres = fiches[choix]
    st.markdown(f"**{nom}** : {points}/{evalues} → {verdict(points, evalues)}")
    for c in criteres:
        icone = {True: "✅", False: "❌", None: "➖"}[c["ok"]]
        st.markdown(f"{icone} **{c['nom']}** — {c['detail']}")


# ---------------------------------------------------------------------------
# Écran 1 : Scanner
# ---------------------------------------------------------------------------


def ecran_scanner():
    st.header("🔎 Scanner 200 WMA")
    st.caption(
        "Moyenne mobile simple sur 200 semaines. "
        "Signal **ACHAT** si le cours est ≤ 200 WMA × 1,05, "
        "puis un score qualité vérifie la santé de l'entreprise."
    )

    nom_indice = st.radio(
        "Indice", ["CAC 40", "Nasdaq 100", "S&P 500"], horizontal=True
    )

    with st.spinner("Téléchargement des données (peut prendre 1 à 2 minutes la première fois)…"):
        composants = composants_indice(nom_indice)
        cours = cours_hebdo(tuple(sorted(composants)))

    if cours.empty:
        st.error("Impossible de récupérer les cours. Réessayez plus tard.")
        return

    # Calcul de la 200 WMA pour chaque action
    lignes = []
    ignorees = 0
    for ticker, nom in composants.items():
        if ticker not in cours.columns:
            ignorees += 1
            continue
        serie = cours[ticker].dropna()
        if len(serie) < PERIODE_WMA:  # pas assez d'historique : on ignore
            ignorees += 1
            continue
        wma = serie.rolling(PERIODE_WMA).mean().iloc[-1]
        prix = serie.iloc[-1]
        ecart = (prix / wma - 1) * 100
        lignes.append(
            {
                "Ticker": ticker,
                "Nom": nom,
                "Cours": prix,
                "200 WMA": wma,
                "Écart %": ecart,
                "Signal": "🟢 ACHAT" if prix <= wma * 1.05 else "",
            }
        )

    if not lignes:
        st.warning("Aucune action avec assez d'historique.")
        return

    tableau = pd.DataFrame(lignes).sort_values("Écart %").reset_index(drop=True)
    nb_achats = (tableau["Signal"] != "").sum()

    col1, col2, col3 = st.columns(3)
    col1.metric("Actions analysées", len(tableau))
    col2.metric("Signaux ACHAT", int(nb_achats))
    col3.metric("Ignorées (< 200 sem.)", ignorees)

    tableau_complet = tableau
    if st.toggle("Afficher seulement les signaux ACHAT"):
        tableau = tableau[tableau["Signal"] != ""]

    st.dataframe(
        tableau,
        hide_index=True,
        width="stretch",
        column_config={
            "Cours": st.column_config.NumberColumn(format="%.2f"),
            "200 WMA": st.column_config.NumberColumn(format="%.2f"),
            "Écart %": st.column_config.NumberColumn(format="%+.1f %%"),
        },
    )
    st.caption(f"Dernière semaine de données : {cours.index[-1]:%d/%m/%Y}. Données mises en cache 24 h.")

    # Score qualité calculé sur le tableau complet (pas seulement le filtre affiché)
    section_qualite(nom_indice, cours, tableau_complet)


# ---------------------------------------------------------------------------
# Écran 2 : Portefeuille
# ---------------------------------------------------------------------------

# Le portefeuille est aussi enregistré dans l'adresse (URL) de la page :
# si vous rechargez la page ou l'ajoutez à l'écran d'accueil de l'iPhone,
# vos lignes sont conservées.


def portefeuille_vers_url():
    """Écrit le portefeuille dans l'URL, ex. ?p=AAPL:150:10,MC.PA:600:2"""
    texte = ",".join(
        f"{l['ticker']}:{l['prix_achat']:g}:{l['quantite']:g}"
        for l in st.session_state.portefeuille
    )
    if texte:
        st.query_params["p"] = texte
    elif "p" in st.query_params:
        del st.query_params["p"]


def portefeuille_depuis_url():
    """Lit le portefeuille depuis l'URL (au premier chargement de la page)."""
    lignes = []
    texte = st.query_params.get("p", "")
    for morceau in texte.split(","):
        try:
            ticker, prix, qte = morceau.split(":")
            lignes.append(
                {"ticker": ticker.upper(), "prix_achat": float(prix), "quantite": float(qte)}
            )
        except ValueError:
            continue  # morceau mal formé : on l'ignore
    return lignes


def graphique(ticker, serie, wma, pivots, provisoire, abc, objectif):
    """Graphique : cours, 200 WMA, ZigZag, points A/B/C et ligne d'objectif."""
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=serie.index, y=serie.values, name="Cours", line=dict(color="#1f77b4")))
    fig.add_trace(go.Scatter(x=wma.index, y=wma.values, name="200 WMA", line=dict(color="#ff7f0e")))

    # Ligne brisée du ZigZag
    points = pivots + ([provisoire] if provisoire else [])
    if points:
        fig.add_trace(
            go.Scatter(
                x=[p["date"] for p in points],
                y=[p["prix"] for p in points],
                name="ZigZag",
                mode="lines+markers",
                line=dict(color="gray", dash="dot", width=1),
                marker=dict(size=5),
            )
        )

    # Points A, B, C
    if abc:
        fig.add_trace(
            go.Scatter(
                x=[p["date"] for p in abc],
                y=[p["prix"] for p in abc],
                mode="markers+text",
                text=["A", "B", "C"],
                textposition="top center",
                marker=dict(size=11, color="purple"),
                name="A / B / C",
            )
        )

    # Ligne horizontale de l'objectif
    if objectif is not None:
        fig.add_hline(
            y=objectif,
            line=dict(color="green", dash="dash"),
            annotation_text=f"Objectif {objectif:.2f}",
            annotation_position="top left",
        )

    fig.update_layout(
        title=ticker,
        height=420,
        margin=dict(l=10, r=10, t=40, b=10),
        legend=dict(orientation="h", y=-0.15),  # légende sous le graphique (mieux sur mobile)
        hovermode="x unified",
    )
    st.plotly_chart(fig, width="stretch")


def ecran_portefeuille():
    st.header("💼 Portefeuille")
    st.caption(
        "Objectif de vente = C + 2,618 × (B − A), avec A = dernier creux majeur, "
        "B = sommet suivant, C = creux suivant (ZigZag). "
        "Signal **VENTE** si cours ≥ objectif × 0,97."
    )

    # Initialisation du portefeuille (depuis l'URL si possible)
    if "portefeuille" not in st.session_state:
        st.session_state.portefeuille = portefeuille_depuis_url()

    # --- Formulaire d'ajout d'une ligne ---
    with st.form("ajout", clear_on_submit=True):
        st.subheader("Ajouter une ligne")
        ticker = st.text_input("Ticker (ex. AAPL, MC.PA)")
        c1, c2 = st.columns(2)
        prix_achat = c1.number_input("Prix d'achat", min_value=0.0, step=1.0, format="%.2f")
        quantite = c2.number_input("Quantité", min_value=0.0, step=1.0, format="%g")
        if st.form_submit_button("➕ Ajouter", width="stretch"):
            if ticker.strip() and prix_achat > 0 and quantite > 0:
                st.session_state.portefeuille.append(
                    {"ticker": ticker.strip().upper(), "prix_achat": prix_achat, "quantite": quantite}
                )
                portefeuille_vers_url()
            else:
                st.warning("Renseignez un ticker, un prix d'achat et une quantité.")

    seuil_pct = st.slider("Seuil du ZigZag (%)", min_value=5, max_value=50, value=20, step=1)
    seuil = seuil_pct / 100

    if not st.session_state.portefeuille:
        st.info("Votre portefeuille est vide. Ajoutez une ligne ci-dessus.")
        return

    # --- Calculs pour chaque ligne ---
    resultats = []
    details = []
    for position, ligne in enumerate(st.session_state.portefeuille):
        t = ligne["ticker"]
        with st.spinner(f"Chargement de {t}…"):
            serie = serie_cours(t)
        if serie.empty:
            st.warning(f"Pas de données pour {t} (ticker incorrect ?).")
            details.append(None)
            continue

        prix = serie.iloc[-1]
        wma = serie.rolling(PERIODE_WMA).mean()
        pivots, provisoire = zigzag(serie, seuil)
        abc = points_abc(pivots)
        objectif = objectif_vente(*abc) if abc else None

        valeur_achat = ligne["prix_achat"] * ligne["quantite"]
        plus_value = (prix - ligne["prix_achat"]) * ligne["quantite"]

        resultats.append(
            {
                "Ticker": t,
                "Cours": prix,
                "Objectif": objectif,
                "% restant": (objectif / prix - 1) * 100 if objectif else None,
                "Plus-value": plus_value,
                "Plus-value %": plus_value / valeur_achat * 100 if valeur_achat else None,
                "Signal": "🔴 VENTE" if objectif and prix >= objectif * 0.97 else "",
            }
        )
        details.append((position, t, serie, wma, pivots, provisoire, abc, objectif, prix))

    # --- Tableau récapitulatif ---
    if resultats:
        st.subheader("Récapitulatif")
        st.dataframe(
            pd.DataFrame(resultats),
            hide_index=True,
            width="stretch",
            column_config={
                "Cours": st.column_config.NumberColumn(format="%.2f"),
                "Objectif": st.column_config.NumberColumn(format="%.2f"),
                "% restant": st.column_config.NumberColumn(format="%+.1f %%"),
                "Plus-value": st.column_config.NumberColumn(format="%+.2f"),
                "Plus-value %": st.column_config.NumberColumn(format="%+.1f %%"),
            },
        )
        st.caption("Les montants sont dans la devise de chaque action (€ pour .PA, $ pour les actions US).")

    # --- Détail et graphique par ligne ---
    st.subheader("Détail par ligne")
    for detail, ligne in zip(details, st.session_state.portefeuille):
        if detail is None:
            continue
        position, t, serie, wma, pivots, provisoire, abc, objectif, prix = detail
        titre = f"{t} — {ligne['quantite']:g} × {ligne['prix_achat']:.2f}"
        with st.expander(titre):
            if abc:
                a, b, c = abc
                st.write(
                    f"**A** (creux) : {a['prix']:.2f} le {a['date']:%d/%m/%Y}  \n"
                    f"**B** (sommet) : {b['prix']:.2f} le {b['date']:%d/%m/%Y}  \n"
                    f"**C** (creux) : {c['prix']:.2f} le {c['date']:%d/%m/%Y}  \n"
                    f"**Objectif** : {objectif:.2f} — cours actuel {prix:.2f}"
                )
            else:
                st.info(
                    "Pas encore de séquence creux → sommet → creux avec ce seuil. "
                    "Essayez un seuil plus petit."
                )
            graphique(t, serie, wma, pivots, provisoire, abc, objectif)
            if st.button("🗑️ Supprimer cette ligne", key=f"suppr_{position}"):
                st.session_state.portefeuille.pop(position)
                portefeuille_vers_url()
                st.rerun()

    # --- Sauvegarde / chargement en CSV (sauvegarde de secours) ---
    with st.expander("💾 Sauvegarder / charger le portefeuille (CSV)"):
        csv = pd.DataFrame(st.session_state.portefeuille).to_csv(index=False)
        st.download_button("Télécharger le CSV", csv, "portefeuille.csv", "text/csv")
        fichier = st.file_uploader("Charger un CSV", type="csv")
        if fichier is not None and st.button("Remplacer le portefeuille par ce fichier"):
            df = pd.read_csv(fichier)
            st.session_state.portefeuille = [
                {
                    "ticker": str(r["ticker"]).upper(),
                    "prix_achat": float(r["prix_achat"]),
                    "quantite": float(r["quantite"]),
                }
                for _, r in df.iterrows()
            ]
            portefeuille_vers_url()
            st.rerun()


# ---------------------------------------------------------------------------
# Navigation entre les deux écrans
# ---------------------------------------------------------------------------
# Des boutons en haut de page plutôt qu'une barre latérale : plus pratique sur iPhone.
ecran = st.radio(
    "Écran", ["🔎 Scanner", "💼 Portefeuille"], horizontal=True, label_visibility="collapsed"
)

if ecran == "🔎 Scanner":
    ecran_scanner()
else:
    ecran_portefeuille()

st.caption("⚠️ Outil pédagogique, pas un conseil en investissement. Données : Yahoo Finance.")
