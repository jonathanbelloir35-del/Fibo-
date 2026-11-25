# -*- coding: utf-8 -*-
"""
Fibo – Opportunités
===================

Un seul écran :
  1. Choix de l'indice (CAC 40, Nasdaq 100, S&P 500).
  2. Un tableau avec, pour chaque action :
       - une NOTE TECHNIQUE sur 10  (200 WMA, Fibonacci, RSI hebdo, rebond)
       - une NOTE FONDAMENTALE sur 10 (chiffre d'affaires, rentabilité, free cash flow, dette, PER)
  3. Une liste déroulante pour ouvrir la FICHE d'une action, avec ses graphiques.

Données : Yahoo Finance (bibliothèque yfinance), cours hebdomadaires sur 10 ans.

Lancer en local :  streamlit run app.py
"""

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from io import StringIO

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import requests
import streamlit as st
import yfinance as yf

st.set_page_config(page_title="Fibo – Opportunités", page_icon="🎯", layout="wide")


# =============================================================================
# 1. RÉGLAGES (modifiables)
# =============================================================================

CACHE_24H = 24 * 60 * 60  # les données sont retéléchargées au plus une fois par jour
PERIODE_WMA = 200  # moyenne mobile 200 semaines
SEUIL_ZIGZAG = 0.20  # 20 % : taille minimale d'une vague pour le ZigZag

# Seuils de la note fondamentale
CROISSANCE_CA_BONNE = 0.05  # croissance annuelle du chiffre d'affaires ≥ 5 %
ROE_BON = 0.12  # rentabilité des capitaux propres ≥ 12 %
DETTE_EBITDA_BONNE = 1.5  # dette nette / EBITDA < 1,5 = 2 points ; < 3 = 1 point

ENTETES_HTTP = {"User-Agent": "Mozilla/5.0 (compatible; fibo-streamlit/2.0)"}


# =============================================================================
# 2. LISTES DES ACTIONS DE CHAQUE INDICE
# =============================================================================

# CAC 40 : liste écrite à la main (à mettre à jour si la composition change)
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

# Banques et assurances du CAC 40 : pour elles, dette et free cash flow ne veulent rien dire
FINANCIERES_CAC40 = {"BNP.PA", "ACA.PA", "GLE.PA", "CS.PA"}

# Nasdaq 100 : liste de secours, utilisée seulement si Wikipédia ne répond pas
NASDAQ100_SECOURS = {
    "AAPL": "Apple",
    "ABNB": "Airbnb",
    "ADBE": "Adobe",
    "ADI": "Analog Devices",
    "ADP": "Automatic Data Processing",
    "ADSK": "Autodesk",
    "AEP": "American Electric Power",
    "AMAT": "Applied Materials",
    "AMD": "Advanced Micro Devices",
    "AMGN": "Amgen",
    "AMZN": "Amazon",
    "APP": "AppLovin",
    "ARM": "Arm Holdings",
    "ASML": "ASML Holding",
    "AVGO": "Broadcom",
    "AXON": "Axon Enterprise",
    "AZN": "AstraZeneca",
    "BIIB": "Biogen",
    "BKNG": "Booking Holdings",
    "BKR": "Baker Hughes",
    "CCEP": "Coca-Cola Europacific Partners",
    "CDNS": "Cadence Design Systems",
    "CDW": "CDW",
    "CEG": "Constellation Energy",
    "CHTR": "Charter Communications",
    "CMCSA": "Comcast",
    "COST": "Costco",
    "CPRT": "Copart",
    "CRWD": "CrowdStrike",
    "CSCO": "Cisco",
    "CSGP": "CoStar Group",
    "CSX": "CSX",
    "CTAS": "Cintas",
    "CTSH": "Cognizant",
    "DASH": "DoorDash",
    "DDOG": "Datadog",
    "DXCM": "DexCom",
    "EA": "Electronic Arts",
    "EXC": "Exelon",
    "FANG": "Diamondback Energy",
    "FAST": "Fastenal",
    "FER": "Ferrovial",
    "FTNT": "Fortinet",
    "GEHC": "GE HealthCare",
    "GFS": "GlobalFoundries",
    "GILD": "Gilead Sciences",
    "GOOG": "Alphabet (classe C)",
    "GOOGL": "Alphabet (classe A)",
    "HON": "Honeywell",
    "IDXX": "IDEXX Laboratories",
    "INTC": "Intel",
    "INTU": "Intuit",
    "ISRG": "Intuitive Surgical",
    "KDP": "Keurig Dr Pepper",
    "KHC": "Kraft Heinz",
    "KLAC": "KLA",
    "LIN": "Linde",
    "LRCX": "Lam Research",
    "LULU": "Lululemon",
    "MAR": "Marriott",
    "MCHP": "Microchip Technology",
    "MDB": "MongoDB",
    "MDLZ": "Mondelez",
    "MELI": "MercadoLibre",
    "META": "Meta Platforms",
    "MNST": "Monster Beverage",
    "MRVL": "Marvell Technology",
    "MSFT": "Microsoft",
    "MSTR": "Strategy (MicroStrategy)",
    "MU": "Micron Technology",
    "NFLX": "Netflix",
    "NVDA": "Nvidia",
    "NXPI": "NXP Semiconductors",
    "ODFL": "Old Dominion Freight Line",
    "ON": "ON Semiconductor",
    "ORLY": "O'Reilly Automotive",
    "PANW": "Palo Alto Networks",
    "PAYX": "Paychex",
    "PCAR": "Paccar",
    "PDD": "PDD Holdings",
    "PEP": "PepsiCo",
    "PLTR": "Palantir",
    "PYPL": "PayPal",
    "QCOM": "Qualcomm",
    "REGN": "Regeneron",
    "ROP": "Roper Technologies",
    "ROST": "Ross Stores",
    "SBUX": "Starbucks",
    "SHOP": "Shopify",
    "SNPS": "Synopsys",
    "TEAM": "Atlassian",
    "TMUS": "T-Mobile US",
    "TRI": "Thomson Reuters",
    "TSLA": "Tesla",
    "TTD": "The Trade Desk",
    "TTWO": "Take-Two Interactive",
    "TXN": "Texas Instruments",
    "VRSK": "Verisk",
    "VRTX": "Vertex Pharmaceuticals",
    "WBD": "Warner Bros. Discovery",
    "WDAY": "Workday",
    "XEL": "Xcel Energy",
    "ZS": "Zscaler",
}


def lire_wikipedia(url, colonnes_ticker, colonnes_nom):
    """Lit le tableau des composants d'un indice sur Wikipédia.

    Renvoie (noms, financieres) : {ticker: nom} et l'ensemble des tickers du secteur financier.
    """
    reponse = requests.get(url, headers=ENTETES_HTTP, timeout=20)
    reponse.raise_for_status()
    for tableau in pd.read_html(StringIO(reponse.text)):
        if isinstance(tableau.columns, pd.MultiIndex):  # en-têtes sur 2 lignes
            tableau.columns = tableau.columns.get_level_values(-1)
        col_ticker = next((c for c in colonnes_ticker if c in tableau.columns), None)
        col_nom = next((c for c in colonnes_nom if c in tableau.columns), None)
        if col_ticker is None or col_nom is None or len(tableau) < 50:
            continue  # ce n'est pas le bon tableau
        # Yahoo Finance écrit "BRK-B" et non "BRK.B"
        tickers = tableau[col_ticker].astype(str).str.strip().str.replace(".", "-", regex=False)
        noms = dict(zip(tickers, tableau[col_nom].astype(str).str.strip()))
        col_secteur = next((c for c in tableau.columns if "Sector" in str(c) or "Industry" in str(c)), None)
        financieres = set()
        if col_secteur is not None:
            financieres = set(tickers[tableau[col_secteur].astype(str).str.contains("Financ")])
        return noms, financieres
    raise ValueError("Tableau des composants introuvable")


@st.cache_data(ttl=CACHE_24H, show_spinner=False)
def composants_indice(nom_indice):
    """Renvoie (noms, financieres) pour l'indice choisi."""
    if nom_indice == "CAC 40":
        return dict(CAC40), set(FINANCIERES_CAC40)

    colonnes_ticker = ["Ticker", "Symbol", "Ticker symbol"]
    colonnes_nom = ["Company", "Security", "Name", "Company name"]

    if nom_indice == "Nasdaq 100":
        try:
            noms, financieres = lire_wikipedia(
                "https://en.wikipedia.org/wiki/Nasdaq-100", colonnes_ticker, colonnes_nom)
            if 90 <= len(noms) <= 110:  # vérification : environ 100 sociétés
                return noms, financieres
        except Exception:
            pass
        return dict(NASDAQ100_SECOURS), set()

    # S&P 500 : Wikipédia, sinon un fichier CSV public sur GitHub
    try:
        return lire_wikipedia(
            "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies", colonnes_ticker, colonnes_nom)
    except Exception:
        url = "https://raw.githubusercontent.com/datasets/s-and-p-500-companies/main/data/constituents.csv"
        df = pd.read_csv(StringIO(requests.get(url, headers=ENTETES_HTTP, timeout=20).text))
        tickers = df["Symbol"].astype(str).str.replace(".", "-", regex=False)
        financieres = set(tickers[df["GICS Sector"].astype(str).str.contains("Financ")])
        return dict(zip(tickers, df["Security"].astype(str))), financieres


# =============================================================================
# 3. TÉLÉCHARGEMENT DES DONNÉES (Yahoo Finance)
# =============================================================================


@st.cache_data(ttl=CACHE_24H, show_spinner=False)
def cours_hebdo(tickers):
    """Cours de clôture HEBDOMADAIRES sur 10 ans : une ligne par semaine, une colonne par action.

    `tickers` est un tuple (et non une liste) pour que le cache fonctionne.
    """
    morceaux = []
    tickers = list(tickers)
    for debut in range(0, len(tickers), 100):  # par paquets de 100 pour ménager Yahoo
        paquet = tickers[debut:debut + 100]
        donnees = yf.download(paquet, period="10y", interval="1wk", auto_adjust=True,
                              progress=False, threads=True)
        if donnees is None or donnees.empty:
            continue
        clotures = donnees["Close"]
        if isinstance(clotures, pd.Series):  # un seul ticker
            clotures = clotures.to_frame(name=paquet[0])
        morceaux.append(clotures)
    if not morceaux:
        return pd.DataFrame()
    resultat = pd.concat(morceaux, axis=1)
    return resultat.loc[:, ~resultat.columns.duplicated()].sort_index()


def _ligne_comptable(tableau, noms):
    """Une ligne d'un état financier : {date de clôture: valeur}, de la plus ancienne à la plus récente."""
    if tableau is None or tableau.empty:
        return {}
    for nom in noms:
        if nom in tableau.index:
            serie = pd.to_numeric(tableau.loc[nom], errors="coerce").dropna().sort_index()
            return {str(d.date()): float(v) for d, v in serie.items()}
    return {}


def _telecharger_comptes(ticker):
    """Comptes annuels d'une action (environ 4 ans), avec 3 tentatives.

    Renvoie (comptes, None) si tout va bien, sinon (None, message d'erreur).
    """
    erreur = "réponse vide"
    for tentative in range(3):
        try:
            action = yf.Ticker(ticker)
            resultat = action.income_stmt
            if resultat is None or resultat.empty:
                raise ValueError("compte de résultat vide (Yahoo limite peut-être les requêtes)")
            bilan, flux = action.balance_sheet, action.cashflow
            return {
                "ca": _ligne_comptable(resultat, ["Total Revenue", "Operating Revenue"]),
                "resultat_net": _ligne_comptable(resultat, ["Net Income", "Net Income Common Stockholders"]),
                "ebitda": _ligne_comptable(resultat, ["EBITDA", "Normalized EBITDA"]),
                "bpa": _ligne_comptable(resultat, ["Diluted EPS", "Basic EPS"]),
                "capitaux_propres": _ligne_comptable(bilan, ["Stockholders Equity", "Common Stock Equity"]),
                "dette": _ligne_comptable(bilan, ["Total Debt"]),
                "tresorerie": _ligne_comptable(
                    bilan, ["Cash Cash Equivalents And Short Term Investments", "Cash And Cash Equivalents"]),
                "fcf": _ligne_comptable(flux, ["Free Cash Flow"]),
            }, None
        except Exception as e:
            erreur = str(e) or e.__class__.__name__
            time.sleep(2 + 3 * tentative)  # on patiente un peu plus à chaque essai
    return None, erreur


@st.cache_resource(show_spinner=False)
def _memoire_comptes():
    """Mémoire partagée {ticker: (heure, comptes)}. On n'y garde QUE les réussites,
    pour que les échecs (blocage Yahoo) soient retentés plus tard."""
    return {}


def comptes_annuels(tickers, afficher_progression=True):
    """Comptes annuels de plusieurs actions. Renvoie (comptes, erreurs)."""
    memoire, maintenant = _memoire_comptes(), time.time()
    comptes, erreurs = {}, {}
    a_telecharger = []
    for t in tickers:
        if t in memoire and maintenant - memoire[t][0] < CACHE_24H:
            comptes[t] = memoire[t][1]
        else:
            a_telecharger.append(t)
    if not a_telecharger:
        return comptes, erreurs

    barre = st.progress(0.0, text="Comptes annuels…") if afficher_progression else None
    with ThreadPoolExecutor(max_workers=3) as executeur:  # 3 à la fois seulement, pour ne pas être bloqué
        taches = {executeur.submit(_telecharger_comptes, t): t for t in a_telecharger}
        for n, tache in enumerate(as_completed(taches), start=1):
            t = taches[tache]
            donnees, erreur = tache.result()
            if donnees is not None:
                memoire[t] = (time.time(), donnees)
                comptes[t] = donnees
            else:
                erreurs[t] = erreur
            if barre:
                barre.progress(n / len(a_telecharger), text=f"Comptes annuels : {n}/{len(a_telecharger)}")
    if barre:
        barre.empty()
    return comptes, erreurs


# =============================================================================
# 4. OUTILS D'ANALYSE TECHNIQUE
# =============================================================================


def rsi(serie, periode=14):
    """RSI de Wilder (0 à 100). Sous 30 = survendu, au-dessus de 70 = suracheté."""
    variation = serie.diff()
    hausses = variation.clip(lower=0).ewm(alpha=1 / periode, adjust=False).mean()
    baisses = (-variation.clip(upper=0)).ewm(alpha=1 / periode, adjust=False).mean()
    return 100 - 100 / (1 + hausses / baisses)


def zigzag(serie, seuil):
    """Repère les sommets et les creux : un sommet est confirmé quand le cours a ensuite
    baissé d'au moins `seuil` (ex. 0.20), un creux quand il a ensuite monté d'au moins `seuil`.

    Renvoie (pivots confirmés, dernier pivot provisoire) ; un pivot = {date, prix, type}.
    """
    valeurs, dates = serie.values, serie.index
    pivots, tendance = [], None
    i_haut = i_bas = i_ext = 0
    for i in range(1, len(valeurs)):
        v = valeurs[i]
        if tendance is None:  # démarrage : on attend un premier mouvement suffisant
            i_haut = i if v > valeurs[i_haut] else i_haut
            i_bas = i if v < valeurs[i_bas] else i_bas
            if v >= valeurs[i_bas] * (1 + seuil):
                pivots.append({"date": dates[i_bas], "prix": valeurs[i_bas], "type": "creux"})
                tendance, i_ext = "hausse", i
            elif v <= valeurs[i_haut] * (1 - seuil):
                pivots.append({"date": dates[i_haut], "prix": valeurs[i_haut], "type": "sommet"})
                tendance, i_ext = "baisse", i
        elif tendance == "hausse":
            if v > valeurs[i_ext]:
                i_ext = i
            elif v <= valeurs[i_ext] * (1 - seuil):
                pivots.append({"date": dates[i_ext], "prix": valeurs[i_ext], "type": "sommet"})
                tendance, i_ext = "baisse", i
        else:
            if v < valeurs[i_ext]:
                i_ext = i
            elif v >= valeurs[i_ext] * (1 + seuil):
                pivots.append({"date": dates[i_ext], "prix": valeurs[i_ext], "type": "creux"})
                tendance, i_ext = "hausse", i
    provisoire = None
    if tendance:
        provisoire = {"date": dates[i_ext], "prix": valeurs[i_ext],
                      "type": "sommet" if tendance == "hausse" else "creux"}
    return pivots, provisoire


def derniere_hausse(pivots, provisoire):
    """Dernière vague de hausse du ZigZag : (creux de départ, sommet). Le sommet peut être provisoire."""
    points = pivots + ([provisoire] if provisoire else [])
    for k in range(len(points) - 2, -1, -1):
        if points[k]["type"] == "creux" and points[k + 1]["type"] == "sommet":
            return points[k], points[k + 1]
    return None


def note_sur_10(criteres):
    """Note sur 10 : chaque critère vaut 2 points. Les critères sans données ne comptent pas.
    Il faut au moins 3 critères évaluables, sinon la note est None."""
    evalues = [c for c in criteres if c["points"] is not None]
    if len(evalues) < 3:
        return None
    return round(sum(c["points"] for c in evalues) / (2 * len(evalues)) * 10, 1)


# =============================================================================
# 5. NOTE TECHNIQUE (sur 10)
# =============================================================================
# 5 critères à 2 points :
#   1. Position par rapport à la 200 WMA   (proche de la moyenne = intéressant)
#   2. 200 WMA en hausse                   (tendance de fond saine)
#   3. Retracement de Fibonacci            (repli de 38,2 à 61,8 % de la dernière hausse)
#   4. RSI hebdomadaire                    (pas suracheté, et qui remonte)
#   5. Rebond : clôture au-dessus de la moyenne 10 semaines


def analyse_technique(serie, seuil=SEUIL_ZIGZAG):
    prix = serie.iloc[-1]
    wma = serie.rolling(PERIODE_WMA).mean()
    mm10 = serie.rolling(10).mean()
    indice_rsi = rsi(serie)
    pivots, provisoire = zigzag(serie, seuil)
    criteres = []

    # 1. Position par rapport à la 200 WMA
    ecart = None
    if pd.notna(wma.iloc[-1]):
        ecart = (prix / wma.iloc[-1] - 1) * 100
        points = 2 if -5 <= ecart <= 5 else 1 if -15 <= ecart <= 20 else 0
        criteres.append({"nom": "Position / 200 WMA", "points": points,
                         "detail": f"Écart {ecart:+.1f} % (2 pts si entre −5 et +5 %, 1 pt entre −15 et +20 %)"})
    else:
        criteres.append({"nom": "Position / 200 WMA", "points": None,
                         "detail": f"Moins de {PERIODE_WMA} semaines d'historique"})

    # 2. Tendance de la 200 WMA (comparée à il y a 20 semaines)
    wma_hausse = None
    if wma.notna().sum() > 20:
        wma_hausse = wma.iloc[-1] > wma.iloc[-21]
        criteres.append({"nom": "200 WMA en hausse", "points": 2 if wma_hausse else 0,
                         "detail": f"{wma.iloc[-21]:.2f} il y a 20 semaines → {wma.iloc[-1]:.2f}"})
    else:
        criteres.append({"nom": "200 WMA en hausse", "points": None, "detail": "Historique trop court"})

    # 3. Retracement de Fibonacci de la dernière hausse
    hausse = derniere_hausse(pivots, provisoire)
    fibo = None
    if hausse and hausse[1]["prix"] > hausse[0]["prix"]:
        a, b = hausse
        amplitude = b["prix"] - a["prix"]
        retracement = (b["prix"] - prix) / amplitude  # 0 = au sommet, 1 = revenu au creux
        fibo = {
            "depart": a, "sommet": b, "retracement": retracement,
            "seuil1": b["prix"] - 0.382 * amplitude,
            "seuil2": b["prix"] - 0.5 * amplitude,
            "seuil3": b["prix"] - 0.618 * amplitude,
        }
        points = 2 if 0.382 <= retracement <= 0.618 else 1 if 0.236 <= retracement <= 0.786 else 0
        criteres.append({"nom": "Retracement de Fibonacci", "points": points,
                         "detail": f"Repli de {retracement:.0%} de la hausse {a['prix']:.2f} → {b['prix']:.2f} "
                                   "(2 pts entre 38,2 et 61,8 %, 1 pt entre 23,6 et 78,6 %)"})
    else:
        criteres.append({"nom": "Retracement de Fibonacci", "points": None, "detail": "Pas de hausse détectée"})

    # 4. RSI hebdomadaire : idéalement entre 30 et 50 et en train de remonter
    r, r_avant = indice_rsi.iloc[-1], indice_rsi.iloc[-3]
    rsi_monte = r > r_avant
    if r <= 50 and rsi_monte:
        points = 2
    elif r <= 50 or (r <= 60 and rsi_monte):
        points = 1
    else:
        points = 0
    criteres.append({"nom": "RSI hebdomadaire", "points": points,
                     "detail": f"RSI {r_avant:.0f} il y a 2 semaines → {r:.0f} "
                               "(2 pts si ≤ 50 et en hausse ; < 30 = survendu, > 70 = suracheté)"})

    # 5. Rebond : clôture au-dessus de la moyenne 10 semaines
    rebond = prix > mm10.iloc[-1]
    criteres.append({"nom": "Rebond (clôture > moyenne 10 sem.)", "points": 2 if rebond else 0,
                     "detail": f"Cours {prix:.2f} / moyenne 10 semaines {mm10.iloc[-1]:.2f}"})

    # Stop de protection : 3 % sous le creux de départ de la dernière hausse
    if fibo and prix > fibo["depart"]["prix"] * 0.97:
        stop = fibo["depart"]["prix"] * 0.97
    else:
        stop = serie.iloc[-10:].min() * 0.97

    return {
        "prix": prix, "wma": wma, "mm10": mm10, "rsi": indice_rsi, "pivots": pivots,
        "provisoire": provisoire, "fibo": fibo, "ecart": ecart, "stop": stop,
        "criteres": criteres, "note": note_sur_10(criteres),
    }


# =============================================================================
# 6. NOTE FONDAMENTALE (sur 10)
# =============================================================================
# 5 critères à 2 points :
#   1. Évolution du chiffre d'affaires
#   2. Rentabilité (ROE)
#   3. Free cash flow
#   4. Dette nette / EBITDA
#   5. PER au cours actuel comparé à son PER moyen des années précédentes


def _valeurs(dico):
    return list(dico.values())


def analyse_fondamentale(comptes, serie, financiere):
    criteres = []
    chiffres = {}  # quelques chiffres clés pour le tableau

    # 1. Chiffre d'affaires : croissance annuelle moyenne (jusqu'à 3 ans) et dernière année
    ca = _valeurs(comptes["ca"])[-4:]
    if len(ca) >= 2 and ca[0] > 0:
        annees = len(ca) - 1
        moyenne = (ca[-1] / ca[0]) ** (1 / annees) - 1
        derniere = ca[-1] / ca[-2] - 1
        chiffres["croissance_ca"] = moyenne * 100
        points = 2 if moyenne >= CROISSANCE_CA_BONNE and derniere >= 0 else 1 if moyenne > 0 else 0
        criteres.append({"nom": "Chiffre d'affaires", "points": points,
                         "detail": f"{moyenne:+.1%} par an sur {annees} an(s), dernière année {derniere:+.1%} "
                                   f"(2 pts si ≥ {CROISSANCE_CA_BONNE:.0%}/an sans recul, 1 pt si positif)"})
    else:
        criteres.append({"nom": "Chiffre d'affaires", "points": None, "detail": "Données absentes"})

    # 2. Rentabilité : ROE = résultat net / capitaux propres
    net, cp = _valeurs(comptes["resultat_net"]), _valeurs(comptes["capitaux_propres"])
    if net and cp:
        if cp[-1] <= 0:
            criteres.append({"nom": "Rentabilité (ROE)", "points": 0, "detail": "Capitaux propres négatifs"})
        else:
            roe = net[-1] / cp[-1]
            chiffres["roe"] = roe * 100
            points = 2 if roe >= ROE_BON else 1 if roe >= ROE_BON / 2 else 0
            criteres.append({"nom": "Rentabilité (ROE)", "points": points,
                             "detail": f"ROE {roe:.1%} (2 pts si ≥ {ROE_BON:.0%}, 1 pt si ≥ {ROE_BON / 2:.0%})"})
    else:
        criteres.append({"nom": "Rentabilité (ROE)", "points": None, "detail": "Données absentes"})

    # 3. Free cash flow (argent réellement encaissé) des 2 dernières années
    fcf = _valeurs(comptes["fcf"])[-2:]
    if financiere:
        criteres.append({"nom": "Free cash flow", "points": None, "detail": "Non applicable (banque / assurance)"})
    elif fcf:
        positifs = sum(v > 0 for v in fcf)
        points = 2 if positifs == len(fcf) else 1 if fcf[-1] > 0 else 0
        texte = ", ".join(f"{v / 1e9:+.2f} Md" for v in fcf)
        criteres.append({"nom": "Free cash flow", "points": points,
                         "detail": f"{texte} (2 pts si toujours positif, 1 pt si la dernière année)"})
    else:
        criteres.append({"nom": "Free cash flow", "points": None, "detail": "Données absentes"})

    # 4. Dette nette / EBITDA
    dette, treso, ebitda = _valeurs(comptes["dette"]), _valeurs(comptes["tresorerie"]), _valeurs(comptes["ebitda"])
    if financiere:
        criteres.append({"nom": "Dette", "points": None, "detail": "Non applicable (banque / assurance)"})
    elif dette or treso:
        dette_nette = (dette[-1] if dette else 0) - (treso[-1] if treso else 0)
        if dette_nette <= 0:
            chiffres["dette_ebitda"] = 0.0
            criteres.append({"nom": "Dette", "points": 2, "detail": "Plus de trésorerie que de dettes"})
        elif ebitda and ebitda[-1] > 0:
            ratio = dette_nette / ebitda[-1]
            chiffres["dette_ebitda"] = ratio
            points = 2 if ratio < DETTE_EBITDA_BONNE else 1 if ratio < 3 else 0
            criteres.append({"nom": "Dette", "points": points,
                             "detail": f"Dette nette / EBITDA = {ratio:.1f} "
                                       f"(2 pts si < {DETTE_EBITDA_BONNE}, 1 pt si < 3)"})
        else:
            criteres.append({"nom": "Dette", "points": 0, "detail": "Endettée avec un EBITDA négatif ou absent"})
    else:
        criteres.append({"nom": "Dette", "points": None, "detail": "Données absentes"})

    # 5. PER au cours actuel, comparé au PER moyen des années précédentes
    #    PER = cours / bénéfice par action (BPA) du dernier exercice publié
    bpa = pd.Series(comptes["bpa"], dtype=float)
    historique_per = {}
    if not bpa.empty:
        bpa.index = pd.to_datetime(bpa.index)
        for date, b in bpa.items():
            prix = serie.asof(date)  # cours à la date de clôture des comptes
            if b > 0 and pd.notna(prix):
                historique_per[date] = prix / b
    if bpa.empty:
        criteres.append({"nom": "PER", "points": None, "detail": "Données absentes"})
    elif bpa.iloc[-1] <= 0:
        criteres.append({"nom": "PER", "points": 0, "detail": "L'entreprise perd de l'argent (BPA négatif)"})
    else:
        per = serie.iloc[-1] / bpa.iloc[-1]
        chiffres["per"] = per
        passes = [v for d, v in historique_per.items() if d < bpa.index[-1]]
        if len(passes) >= 2:
            moyenne = sum(passes) / len(passes)
            chiffres["per_moyen"] = moyenne
            points = 2 if per <= moyenne * 0.9 else 1 if per <= moyenne * 1.1 else 0
            criteres.append({"nom": "PER", "points": points,
                             "detail": f"PER actuel {per:.1f} contre {moyenne:.1f} en moyenne avant "
                                       "(2 pts si 10 % moins cher, 1 pt si à peu près égal)"})
        else:
            criteres.append({"nom": "PER", "points": None, "detail": f"PER actuel {per:.1f}, historique trop court"})

    return {"criteres": criteres, "note": note_sur_10(criteres), "chiffres": chiffres,
            "historique_per": historique_per}


# =============================================================================
# 7. TABLEAU DE L'INDICE
# =============================================================================


@st.cache_data(ttl=CACHE_24H, show_spinner="Analyse technique de toutes les actions…")
def notes_techniques(noms, cours):
    """Note technique de chaque action de l'indice (rapide : seulement les cours)."""
    lignes = []
    for ticker, nom in noms.items():
        if ticker not in cours.columns:
            continue
        serie = cours[ticker].dropna()
        if len(serie) < 60:  # au moins un an d'historique
            continue
        t = analyse_technique(serie)
        fibo = t["fibo"]
        lignes.append({
            "Ticker": ticker, "Nom": nom, "Cours": t["prix"],
            "Note technique": t["note"],
            "Écart 200 WMA %": t["ecart"],
            "Repli Fibo %": fibo["retracement"] * 100 if fibo else None,
            "RSI": t["rsi"].iloc[-1],
            "Seuil 1": fibo["seuil1"] if fibo else None,
            "Seuil 2": fibo["seuil2"] if fibo else None,
            "Seuil 3": fibo["seuil3"] if fibo else None,
            "Stop": t["stop"],
        })
    return pd.DataFrame(lignes)


def verdict(note_tech, note_fond):
    """Résumé en une icône à partir des deux notes."""
    if pd.isna(note_fond):
        return ""
    if note_tech >= 7 and note_fond >= 7:
        return "🎯 Opportunité"
    if note_fond >= 7:
        return "👀 Surveiller"
    if note_fond < 4:
        return "⛔ Fragile"
    return "🟡 Moyenne"


# =============================================================================
# 8. GRAPHIQUES DE LA FICHE ACTION
# =============================================================================


# Sans la barre d'outils de Plotly, qui cache le titre des graphiques sur iPhone
SANS_OUTILS = {"displayModeBar": False}


def graphique_cours(ticker, serie, t):
    """Cours, 200 WMA, moyenne 10 semaines, ZigZag, zone d'achat (seuils 1 à 3) et stop, sur 5 ans."""
    debut = serie.index[max(0, len(serie) - 260)]
    visible = serie[serie.index >= debut]
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=visible.index, y=visible.values, name="Cours", line=dict(color="#1f77b4")))
    fig.add_trace(go.Scatter(x=visible.index, y=t["wma"][visible.index].values, name="200 WMA",
                             line=dict(color="#ff7f0e", width=2)))
    fig.add_trace(go.Scatter(x=visible.index, y=t["mm10"][visible.index].values, name="Moy. 10 sem.",
                             line=dict(color="gray", width=1, dash="dot")))
    points = [p for p in t["pivots"] + ([t["provisoire"]] if t["provisoire"] else []) if p["date"] >= debut]
    if points:
        fig.add_trace(go.Scatter(x=[p["date"] for p in points], y=[p["prix"] for p in points], name="ZigZag",
                                 mode="lines+markers", line=dict(color="purple", width=1, dash="dash"),
                                 marker=dict(size=5)))
    niveaux = list(visible.values) + [t["stop"]]
    if t["fibo"]:
        f = t["fibo"]
        fig.add_hrect(y0=f["seuil3"], y1=f["seuil1"], fillcolor="green", opacity=0.12, line_width=0)
        for nom, cle in [("Seuil 1", "seuil1"), ("Seuil 2", "seuil2"), ("Seuil 3", "seuil3")]:
            fig.add_hline(y=f[cle], line=dict(color="green", width=1, dash="dot"),
                          annotation_text=f"{nom} {f[cle]:.2f}", annotation_position="top left")
        niveaux += [f["seuil1"], f["seuil3"]]
    fig.add_hline(y=t["stop"], line=dict(color="red", dash="dash"),
                  annotation_text=f"Stop {t['stop']:.2f}", annotation_position="bottom left")
    marge = (max(niveaux) - min(niveaux)) * 0.05
    fig.update_yaxes(range=[min(niveaux) - marge, max(niveaux) + marge])
    fig.update_layout(title=f"{ticker} — 5 ans (hebdomadaire)", height=430, hovermode="x unified",
                      margin=dict(l=10, r=10, t=40, b=10), legend=dict(orientation="h", y=-0.15))
    st.plotly_chart(fig, width="stretch", config=SANS_OUTILS)


def graphique_rsi(t):
    visible = t["rsi"].iloc[-156:]  # 3 ans
    fig = go.Figure(go.Scatter(x=visible.index, y=visible.values, name="RSI", line=dict(color="#9467bd")))
    fig.add_hline(y=70, line=dict(color="red", dash="dot", width=1), annotation_text="70 suracheté")
    fig.add_hline(y=30, line=dict(color="green", dash="dot", width=1), annotation_text="30 survendu")
    fig.update_layout(title="RSI hebdomadaire (14 semaines)", height=220, yaxis=dict(range=[0, 100]),
                      margin=dict(l=10, r=10, t=40, b=10))
    st.plotly_chart(fig, width="stretch", config=SANS_OUTILS)


def graphique_fondamentaux(comptes, historique_per):
    """Barres : chiffre d'affaires, résultat net et free cash flow par année (en milliards)."""
    fig = go.Figure()
    for cle, nom, couleur in [("ca", "Chiffre d'affaires", "#1f77b4"),
                              ("resultat_net", "Résultat net", "#2ca02c"),
                              ("fcf", "Free cash flow", "#ff7f0e")]:
        donnees = comptes.get(cle, {})
        if donnees:
            annees = [d[:4] for d in donnees]
            fig.add_trace(go.Bar(x=annees, y=[v / 1e9 for v in donnees.values()], name=nom,
                                 marker_color=couleur))
    fig.update_layout(title="Comptes annuels (milliards)", barmode="group", height=320,
                      margin=dict(l=10, r=10, t=40, b=10), legend=dict(orientation="h", y=-0.2))
    st.plotly_chart(fig, width="stretch", config=SANS_OUTILS)

    if historique_per:
        fig_per = go.Figure(go.Bar(x=[str(d.year) for d in historique_per], y=list(historique_per.values()),
                                   name="PER", marker_color="#9467bd"))
        fig_per.update_layout(title="PER à chaque clôture annuelle", height=240,
                              margin=dict(l=10, r=10, t=40, b=10))
        st.plotly_chart(fig_per, width="stretch", config=SANS_OUTILS)


def afficher_criteres(criteres):
    for c in criteres:
        if c["points"] is None:
            icone, score = "➖", "—"
        else:
            icone, score = {2: "✅", 1: "🟡", 0: "❌"}[c["points"]], f"{c['points']}/2"
        st.markdown(f"{icone} **{c['nom']}** ({score}) — {c['detail']}")


# =============================================================================
# 9. FICHE ACTION
# =============================================================================


def fiche_action(ticker, nom, serie, financiere):
    st.subheader(f"📋 {nom} ({ticker})")
    t = analyse_technique(serie)

    comptes, erreurs = comptes_annuels([ticker], afficher_progression=False)
    f = analyse_fondamentale(comptes[ticker], serie, financiere) if ticker in comptes else None

    c1, c2, c3 = st.columns(3)
    c1.metric("Cours", f"{t['prix']:.2f}")
    c2.metric("Note technique", f"{t['note']}/10" if t["note"] is not None else "—")
    c3.metric("Note fondamentale", f"{f['note']}/10" if f and f["note"] is not None else "—")

    onglet_tech, onglet_fond = st.tabs(["📈 Analyse technique", "🏢 Analyse fondamentale"])

    with onglet_tech:
        afficher_criteres(t["criteres"])
        if t["fibo"]:
            fb = t["fibo"]
            seuils = pd.DataFrame([
                {"Seuil": "Seuil 1 (repli 38,2 %)", "Prix": fb["seuil1"]},
                {"Seuil": "Seuil 2 (repli 50 %)", "Prix": fb["seuil2"]},
                {"Seuil": "Seuil 3 (repli 61,8 %)", "Prix": fb["seuil3"]},
            ])
            seuils["Distance au cours"] = (seuils["Prix"] / t["prix"] - 1) * 100
            st.markdown("**Seuils d'achat (achat en 3 tranches)**")
            st.dataframe(seuils, hide_index=True, width="stretch", column_config={
                "Prix": st.column_config.NumberColumn(format="%.2f"),
                "Distance au cours": st.column_config.NumberColumn(format="%+.1f %%")})
        st.markdown(f"🛑 **Stop de protection suggéré : {t['stop']:.2f}** "
                    f"({(t['stop'] / t['prix'] - 1) * 100:+.1f} % par rapport au cours)")
        graphique_cours(ticker, serie, t)
        graphique_rsi(t)

    with onglet_fond:
        if f is None:
            st.warning(f"Comptes indisponibles ({erreurs.get(ticker, 'erreur inconnue')}). "
                       "Yahoo limite peut-être les requêtes : réessayez dans quelques minutes.")
            if st.button("🔄 Réessayer", key="reessayer_fiche"):
                st.rerun()
        else:
            afficher_criteres(f["criteres"])
            graphique_fondamentaux(comptes[ticker], f["historique_per"])
            st.caption("Montants dans la devise des comptes de l'entreprise. "
                       "Le PER est calculé avec le bénéfice par action du dernier exercice publié.")


# =============================================================================
# 10. ÉCRAN PRINCIPAL
# =============================================================================


# --- Filtres de valorisation (croissance du CA, PER actuel / PER moyen) ---------------------------
# D'où viennent les données :
#   - Chiffre d'affaires et bénéfice par action (BPA) : comptes annuels publiés, fournis par Yahoo Finance
#     (compte de résultat annuel). Yahoo ne donne qu'environ 4 exercices.
#   - Cours : cours hebdomadaires Yahoo Finance (ajustés des divisions d'actions et dividendes).
#   - PER d'une année = cours à la date de clôture de l'exercice / BPA de cet exercice.
#   - PER actuel = dernier cours / BPA du dernier exercice publié.

PER_MAX_AUTORISE = 100  # au-delà, le PER n'a plus beaucoup de sens (bénéfice quasi nul)
PER_MIN_PLAUSIBLE = 3   # en dessous, presque toujours une erreur : comptes publiés dans une autre devise que
                        # le cours (ex. PDD : yuans contre dollars) ou BPA erroné chez Yahoo (ex. Trade Desk)
PERIODE_1AN, PERIODE_3ANS = "1 an", "Moyenne 3 ans"

# Réglages mémorisés dans l'adresse de la page : clé du widget -> (nom dans l'URL, type, valeur par défaut)
REGLAGES = {
    "opp_indice": ("indice", str, "CAC 40"),
    "f_ca_min": ("ca_min", int, 5),
    "f_ca_periode": ("ca_periode", str, PERIODE_1AN),
    "f_per_max": ("per_max", float, 0.9),
}
VALEURS_AUTORISEES = {"opp_indice": ["CAC 40", "Nasdaq 100", "S&P 500"],
                      "f_ca_periode": [PERIODE_1AN, PERIODE_3ANS]}


def charger_reglages():
    """Au premier affichage, reprend les derniers réglages enregistrés dans l'adresse de la page."""
    for cle, (param, typ, defaut) in REGLAGES.items():
        if cle in st.session_state:
            continue
        valeur = defaut
        try:
            if param in st.query_params:
                valeur = typ(st.query_params[param])
        except ValueError:
            valeur = defaut
        if cle in VALEURS_AUTORISEES and valeur not in VALEURS_AUTORISEES[cle]:
            valeur = defaut
        if cle == "f_ca_min":
            valeur = min(30, max(-10, valeur))
        if cle == "f_per_max":
            valeur = min(1.5, max(0.5, round(valeur * 20) / 20))  # pas de 0,05
        st.session_state[cle] = valeur


def sauver_reglages():
    """Enregistre les réglages actuels dans l'adresse de la page (retrouvés au prochain chargement)."""
    for cle, (param, _, _) in REGLAGES.items():
        if cle in st.session_state:
            st.query_params[param] = str(st.session_state[cle])


def valorisation(comptes, serie):
    """Croissance du CA et PER (actuel, moyen sur 5 ans au plus) d'une action.

    Renvoie un dict avec les valeurs (None si impossible) et la liste des données manquantes."""
    r = {"ca_1an": None, "ca_3ans": None, "per": None, "per_moyen": None, "annees_per": 0,
         "ratio": None, "probleme": None, "manques": []}
    ca = list(comptes.get("ca", {}).values())
    if len(ca) >= 2 and ca[-2] > 0:
        r["ca_1an"] = (ca[-1] / ca[-2] - 1) * 100
    else:
        r["manques"].append("CA : moins de 2 années")
    if len(ca) >= 4 and ca[-4] > 0:
        r["ca_3ans"] = ((ca[-1] / ca[-4]) ** (1 / 3) - 1) * 100
    elif len(ca) >= 2:
        r["manques"].append(f"CA : {len(ca)} années seulement, moyenne 3 ans impossible")

    bpa = pd.Series(comptes.get("bpa", {}), dtype=float)
    if bpa.empty:
        r["probleme"] = "BPA (bénéfice par action) absent chez Yahoo"
        return r
    bpa.index = pd.to_datetime(bpa.index)
    bpa = bpa.sort_index()
    if bpa.iloc[-1] <= 0:
        r["probleme"] = "PER négatif (l'entreprise perd de l'argent)"
        return r
    r["per"] = serie.iloc[-1] / bpa.iloc[-1]
    if r["per"] < PER_MIN_PLAUSIBLE:
        r["probleme"] = (f"PER anormalement bas ({r['per']:.1f}) : comptes dans une autre devise que le cours, "
                         "ou erreur de données chez Yahoo")
        return r
    if r["per"] > PER_MAX_AUTORISE:
        r["probleme"] = f"PER supérieur à {PER_MAX_AUTORISE} ({r['per']:.0f})"
        return r

    # PER à chaque clôture annuelle des 5 dernières années (années bénéficiaires, PER ≤ 100)
    historiques = []
    for date, b in bpa.iloc[-5:].items():
        prix = serie.asof(date)
        if b > 0 and pd.notna(prix) and prix / b <= PER_MAX_AUTORISE:
            historiques.append(prix / b)
    r["annees_per"] = len(historiques)
    if len(historiques) < 2:
        r["probleme"] = f"PER historique insuffisant ({len(historiques)} année utilisable)"
        return r
    if len(historiques) < 4:  # Yahoo fournit au mieux 4 exercices : on ne signale que les cas plus courts
        r["manques"].append(f"PER moyen sur {len(historiques)} ans seulement (années en perte ou PER > 100 écartées)")
    r["per_moyen"] = sum(historiques) / len(historiques)
    r["ratio"] = r["per"] / r["per_moyen"]
    return r


def main():
    st.title("🎯 Opportunités")
    st.caption("Filtrez les actions sur leur croissance et leur prix (PER), puis consultez leurs notes "
               "technique et fondamentale.")
    charger_reglages()

    nom_indice = st.radio("Indice", VALEURS_AUTORISEES["opp_indice"], horizontal=True, key="opp_indice")

    # --- Zone de filtres ---
    with st.container(border=True):
        st.markdown("**🎛️ Filtres**")
        c1, c2 = st.columns([2, 1], vertical_alignment="bottom")
        ca_min = c1.slider("Croissance du CA minimum (%)", -10, 30, step=1, key="f_ca_min", format="%+d %%")
        periode = c2.selectbox("Période", [PERIODE_1AN, PERIODE_3ANS], key="f_ca_periode")
        per_max = st.slider("Ratio PER actuel / PER moyen 5 ans maximum", 0.5, 1.5, step=0.05,
                            key="f_per_max", format="%.2f")
        ecart = abs(per_max - 1) * 100
        if per_max < 1:
            st.caption(f"Ratio {per_max:.2f} = PER actuel {ecart:.0f} % sous sa moyenne : "
                       f"**moins cher que d'habitude**".replace(".", ","))
        elif per_max > 1:
            st.caption(f"Ratio {per_max:.2f} = PER actuel {ecart:.0f} % au-dessus de sa moyenne : "
                       f"**plus cher que d'habitude**".replace(".", ","))
        else:
            st.caption("Ratio 1,00 = PER actuel égal à sa moyenne : au même prix que d'habitude")
        st.caption("PER moyen calculé sur les clôtures annuelles disponibles, 4 ans au plus "
                   "(Yahoo Finance ne fournit pas 5 ans de comptes).")
    sauver_reglages()

    with st.spinner("Téléchargement des cours (1 à 2 minutes la première fois)…"):
        noms, financieres = composants_indice(nom_indice)
        cours = cours_hebdo(tuple(sorted(noms)))
    if cours.empty:
        st.error("Impossible de récupérer les cours. Réessayez plus tard.")
        return

    # --- Note technique de toutes les actions ---
    tableau = notes_techniques(noms, cours)
    if tableau.empty:
        st.warning("Aucune action analysable.")
        return

    # --- Comptes annuels de TOUTES les actions de l'indice (nécessaires pour filtrer) ---
    comptes, erreurs = comptes_annuels(list(tableau["Ticker"]))
    if erreurs:
        st.warning(f"Comptes indisponibles pour {len(erreurs)} action(s) : Yahoo limite sans doute les requêtes. "
                   "Patientez quelques minutes puis appuyez sur « Réessayer ».")
        if st.button("🔄 Réessayer"):
            st.rerun()

    # --- Valorisation, note fondamentale et application des filtres ---
    lignes, exclues, incompletes = [], [], []
    for _, ligne in tableau.iterrows():
        t = ligne["Ticker"]
        if t not in comptes:
            exclues.append({"Ticker": t, "Nom": ligne["Nom"], "Problème": "Comptes indisponibles (Yahoo)"})
            continue
        serie = cours[t].dropna()
        v = valorisation(comptes[t], serie)
        croissance = v["ca_1an"] if periode == PERIODE_1AN else v["ca_3ans"]
        probleme = v["probleme"]
        if probleme is None and croissance is None:
            probleme = "CA manquant pour la période choisie"
        if probleme:
            exclues.append({"Ticker": t, "Nom": ligne["Nom"], "Problème": probleme})
            continue
        if v["manques"]:
            incompletes.append({"Ticker": t, "Nom": ligne["Nom"], "Donnée manquante": " ; ".join(v["manques"])})
        if croissance < ca_min or v["ratio"] > per_max + 1e-9:
            continue  # ne passe pas les filtres
        f = analyse_fondamentale(comptes[t], serie, t in financieres)
        lignes.append({**ligne.to_dict(), "Croissance CA %": croissance, "PER actuel": v["per"],
                       "PER moyen": v["per_moyen"], "Ratio PER": v["ratio"], "Années PER": v["annees_per"],
                       "Note fondamentale": f["note"], "Dette/EBITDA": f["chiffres"].get("dette_ebitda"),
                       "Verdict": verdict(ligne["Note technique"], f["note"] if f["note"] is not None else np.nan)})

    c1, c2, c3 = st.columns(3)
    c1.metric("Actions retenues", len(lignes), help="Actions qui passent les deux filtres")
    c2.metric("Actions analysées", len(tableau))
    c3.metric("⚠️ Exclues (données / PER)", len(exclues),
              help="PER négatif ou supérieur à 100, ou donnée manquante : voir le détail plus bas")

    if not lignes:
        st.info("Aucune action ne passe les filtres. Assouplissez-les (croissance plus basse, ratio plus haut).")
        afficher_donnees_manquantes(exclues, incompletes)
        return

    # --- Tri par ratio PER croissant (les moins chères par rapport à leur habitude d'abord) ---
    resultat = pd.DataFrame(lignes).sort_values("Ratio PER")
    recherche = st.text_input("🔍 Rechercher (ticker ou nom)", placeholder="ex. NVDA ou LVMH")
    affiche = resultat
    if recherche.strip():
        texte = recherche.strip().lower()
        affiche = resultat[resultat["Ticker"].str.lower().str.contains(texte, regex=False)
                           | resultat["Nom"].str.lower().str.contains(texte, regex=False)]

    note = lambda titre: st.column_config.NumberColumn(titre, format="%.1f /10")  # chiffre compact (iPhone)
    prix = st.column_config.NumberColumn(format="%.2f")
    colonnes = ["Ticker", "Nom", "Croissance CA %", "PER actuel", "PER moyen", "Ratio PER", "Années PER",
                "Verdict", "Note technique", "Note fondamentale", "Cours", "Écart 200 WMA %", "Repli Fibo %",
                "RSI", "Dette/EBITDA", "Seuil 1", "Seuil 2", "Seuil 3", "Stop"]
    st.dataframe(
        affiche[colonnes], hide_index=True, width="stretch",
        height=min(420, 35 * (len(affiche) + 1) + 3),  # hauteur adaptée au nombre d'actions
        column_config={
            "Ticker": st.column_config.TextColumn(pinned=True),  # reste visible pendant le défilement
            "Nom": st.column_config.TextColumn(width="medium"),
            "Croissance CA %": st.column_config.NumberColumn(
                f"Croissance CA ({'1 an' if periode == PERIODE_1AN else 'moy. 3 ans'})", format="%+.1f %%"),
            "PER actuel": st.column_config.NumberColumn(format="%.1f"),
            "PER moyen": st.column_config.NumberColumn("PER moyen 5 ans", format="%.1f",
                                                       help="Moyenne des PER aux clôtures annuelles disponibles"),
            "Ratio PER": st.column_config.NumberColumn(format="%.2f", help="< 1 : moins cher que d'habitude"),
            "Années PER": st.column_config.NumberColumn(format="%d", help="Nombre d'années dans le PER moyen"),
            "Verdict": st.column_config.TextColumn(width="medium"),
            "Note technique": note("Note tech."),
            "Note fondamentale": note("Note fond."),
            "Cours": prix, "Seuil 1": prix, "Seuil 2": prix, "Seuil 3": prix, "Stop": prix,
            "Écart 200 WMA %": st.column_config.NumberColumn(format="%+.1f %%"),
            "Repli Fibo %": st.column_config.NumberColumn(format="%.0f %%"),
            "RSI": st.column_config.NumberColumn(format="%.0f"),
            "Dette/EBITDA": st.column_config.NumberColumn(format="%.1f"),
        },
    )
    st.caption(
        "Trié du ratio PER le plus bas (le moins cher par rapport à son habitude) au plus haut. "
        "« Années PER » : nombre de clôtures annuelles utilisées pour le PER moyen (Yahoo en fournit 4 au plus). "
        "🎯 Opportunité : notes technique et fondamentale ≥ 7 · 👀 Surveiller · 🟡 Moyenne · ⛔ Fragile. "
        f"Faites glisser le tableau pour voir toutes les colonnes. Dernière semaine de cours : {cours.index[-1]:%d/%m/%Y}."
    )
    afficher_donnees_manquantes(exclues, incompletes)

    # --- Fiche action ---
    st.divider()
    if affiche.empty:
        st.info("Aucune action ne correspond à la recherche.")
        return
    choix = st.selectbox("Voir la fiche de l'action", affiche["Ticker"],
                         format_func=lambda t: f"{t} — {noms.get(t, t)}")
    fiche_action(choix, noms.get(choix, choix), cours[choix].dropna(), choix in financieres)


def afficher_donnees_manquantes(exclues, incompletes):
    """Prévient des données manquantes : actions exclues, et actions affichées avec des données partielles."""
    if exclues:
        with st.expander(f"⚠️ Actions exclues ({len(exclues)}) : PER négatif, supérieur à {PER_MAX_AUTORISE} "
                         "ou anormal, ou donnée manquante"):
            st.dataframe(pd.DataFrame(exclues), hide_index=True, width="stretch",
                         column_config={"Problème": st.column_config.TextColumn(width="large")})
    if incompletes:
        with st.expander(f"ℹ️ Données partielles ({len(incompletes)} action(s))"):
            st.caption("Ces actions restent analysées, mais avec moins d'historique que les autres.")
            st.dataframe(pd.DataFrame(incompletes), hide_index=True, width="stretch",
                         column_config={"Donnée manquante": st.column_config.TextColumn(width="large")})


# =============================================================================
# 11. PAGE « ALERTE ACHAT »
# =============================================================================
# Regroupe, sur les indices choisis, les actions dont :
#   - le RSI hebdomadaire est inférieur à 40 (l'action a beaucoup baissé récemment)
#   - ET la note fondamentale est supérieure ou égale à 7 (l'entreprise est solide)

RSI_ALERTE = 40  # valeur proposée par défaut ; réglable avec le curseur de la page
NOTE_FOND_ALERTE = 7.0  # valeur proposée par défaut ; réglable avec le curseur de la page


def page_alerte_achat():
    st.title("🚨 Alerte achat")
    # Curseur : seuil de RSI en dessous duquel une action déclenche une alerte achat
    seuil_rsi = st.slider("Alerte si RSI hebdomadaire inférieur à", 15, 60, RSI_ALERTE, key="alerte_rsi",
                          help="Plus le seuil est bas, plus l'action doit avoir baissé fortement "
                               "(30 = survente classique). Plus il est haut, plus il y a d'alertes, "
                               "et plus le calcul est long (comptes de chaque action à télécharger).")
    # Curseur : note fondamentale minimale (santé financière de l'entreprise)
    note_min = st.slider("Note fondamentale minimale (sur 10)", 0.0, 10.0, NOTE_FOND_ALERTE, 0.5,
                         key="alerte_note",
                         help="Plus la note est haute, plus l'entreprise doit être solide "
                              "(croissance, rentabilité, free cash flow, dette, PER). 7 = bonne santé.")
    st.caption(f"Actions avec un **RSI hebdomadaire < {seuil_rsi}** et une "
               f"**note fondamentale ≥ {note_min:g}/10**.")

    indices = st.multiselect("Indices surveillés", ["CAC 40", "Nasdaq 100", "S&P 500"],
                             default=["CAC 40", "Nasdaq 100", "S&P 500"], key="alerte_indices")
    if not indices:
        st.info("Choisissez au moins un indice.")
        return

    # --- 1. RSI de toutes les actions (rapide : seulement les cours) ---
    candidats = []  # une ligne par action avec RSI < 40
    noms_tous, financieres_toutes, series = {}, set(), {}
    with st.spinner("Téléchargement des cours (1 à 2 minutes la première fois)…"):
        for nom_indice in indices:
            noms, financieres = composants_indice(nom_indice)
            cours = cours_hebdo(tuple(sorted(noms)))
            if cours.empty:
                st.warning(f"Cours indisponibles pour le {nom_indice}.")
                continue
            tableau = notes_techniques(noms, cours)
            if tableau.empty:
                continue
            financieres_toutes |= financieres
            for _, ligne in tableau[tableau["RSI"] < seuil_rsi].iterrows():
                if ligne["Ticker"] in series:  # action présente dans 2 indices (ex. Nasdaq 100 et S&P 500)
                    continue
                series[ligne["Ticker"]] = cours[ligne["Ticker"]].dropna()
                noms_tous[ligne["Ticker"]] = ligne["Nom"]
                candidats.append({**ligne.to_dict(), "Indice": nom_indice})

    if not candidats:
        st.success(f"Aucune action n'a un RSI hebdomadaire inférieur à {seuil_rsi} en ce moment.")
        return

    # --- 2. Note fondamentale de ces actions seulement (plus lent) ---
    st.caption(f"{len(candidats)} action(s) avec un RSI < {seuil_rsi} : calcul de leur note fondamentale…")
    comptes, erreurs = comptes_annuels([c["Ticker"] for c in candidats])
    alertes = []
    for c in candidats:
        t = c["Ticker"]
        if t not in comptes:
            continue
        f = analyse_fondamentale(comptes[t], series[t], t in financieres_toutes)
        if f["note"] is not None and f["note"] >= note_min:
            alertes.append({**c, "Note fondamentale": f["note"],
                            "Croissance CA %/an": f["chiffres"].get("croissance_ca"),
                            "PER": f["chiffres"].get("per")})

    if erreurs:
        st.warning(f"Comptes indisponibles pour {len(erreurs)} action(s) : la liste est peut-être incomplète. "
                   "Yahoo limite sans doute les requêtes : patientez quelques minutes puis appuyez sur « Réessayer ».")
        if st.button("🔄 Réessayer", key="alerte_reessayer"):
            st.rerun()

    c1, c2 = st.columns(2)
    c1.metric(f"RSI < {seuil_rsi}", len(candidats))
    c2.metric("🚨 Alertes achat", len(alertes))

    if not alertes:
        st.info(f"Aucune action ne remplit les deux conditions pour le moment "
                f"(note fondamentale ≥ {note_min:g} et RSI < {seuil_rsi}).")
        return

    # Tableau trié du RSI le plus bas (le plus survendu) au plus haut
    resultat = pd.DataFrame(alertes).sort_values("RSI")
    prix = st.column_config.NumberColumn(format="%.2f")
    colonnes = ["Ticker", "Nom", "RSI", "Note fondamentale", "Note technique", "Cours", "Indice",
                "Écart 200 WMA %", "Croissance CA %/an", "PER", "Seuil 1", "Seuil 2", "Seuil 3", "Stop"]
    st.dataframe(
        resultat[colonnes], hide_index=True, width="stretch",
        column_config={
            "Ticker": st.column_config.TextColumn(pinned=True),
            "Nom": st.column_config.TextColumn(width="medium"),
            "RSI": st.column_config.NumberColumn(format="%.0f"),
            "Note fondamentale": st.column_config.NumberColumn("Note fond.", format="%.1f /10"),
            "Note technique": st.column_config.NumberColumn("Note tech.", format="%.1f /10"),
            "Cours": prix, "Seuil 1": prix, "Seuil 2": prix, "Seuil 3": prix, "Stop": prix,
            "Écart 200 WMA %": st.column_config.NumberColumn(format="%+.1f %%"),
            "Croissance CA %/an": st.column_config.NumberColumn(format="%+.1f %%"),
            "PER": st.column_config.NumberColumn(format="%.1f"),
        },
    )
    st.caption("Trié du RSI le plus bas au plus haut. Un RSI bas signale une forte baisse récente : "
               "attendez de préférence que le rebond commence (voir la fiche). "
               "Faites glisser le tableau pour voir toutes les colonnes.")

    # --- Fiche action ---
    st.divider()
    choix = st.selectbox("Voir la fiche de l'action", resultat["Ticker"],
                         format_func=lambda t: f"{t} — {noms_tous.get(t, t)}", key="alerte_choix")
    fiche_action(choix, noms_tous.get(choix, choix), series[choix], choix in financieres_toutes)


# =============================================================================
# 12. PAGE « TEST HISTORIQUE » (backtest)
# =============================================================================
# On simule un PORTEFEUILLE, semaine après semaine, sur les cours de clôture hebdomadaires :
#   - capital de départ (ex. 10 000 €), chaque achat au maximum de 1 000 € (selon l'argent disponible)
#   - VENTE  quand le RSI hebdomadaire d'une action détenue dépasse le seuil de surachat (ex. 70)
#   - ACHAT  quand le RSI hebdomadaire passe sous le seuil de survente (ex. 30),
#            en commençant par les actions les plus survendues, tant qu'il reste de l'argent
#   - Une seule position à la fois par action.
#
# Filtre fondamental (au choix) :
#   - « Aucune note »      : aucun filtre sur la santé financière.
#   - « Note de l'époque » : seulement les comptes publiés AVANT l'achat (honnête, mais Yahoo ne
#                            donne qu'environ 4 ans de comptes : peu d'achats avant ~2023).
#   - « Note d'aujourd'hui » : note actuelle appliquée au passé (résultat trop optimiste).

DELAI_PUBLICATION = pd.Timedelta(days=90)  # les comptes annuels sont publiés ~3 mois après la clôture
MODE_SANS_NOTE = "Aucune note (pas de filtre)"
MODE_EPOQUE = "Note de l'époque (honnête, peu d'achats avant 2023)"
MODE_AUJOURDHUI = "Note d'aujourd'hui (trop optimiste)"
INDICES_YAHOO = {"CAC 40": "^FCHI", "Nasdaq 100": "^NDX", "S&P 500": "^GSPC"}  # pour la comparaison
ACHAT_MINIMUM = 100  # on n'achète pas avec moins de 100 € disponibles


def comptes_a_la_date(comptes, date):
    """Ne garde que les comptes déjà publiés à `date`."""
    limite = date - DELAI_PUBLICATION
    return {cle: {d: v for d, v in valeurs.items() if pd.Timestamp(d) <= limite}
            for cle, valeurs in comptes.items()}


class FiltreFondamental:
    """Dit si une action peut être achetée à une date donnée, selon le mode choisi."""

    def __init__(self, mode, cours, comptes, financieres, note_min, valo=None):
        """valo : None, ou dict des filtres de valorisation (comme l'écran Opportunités) :
        {"ca_min": 5, "periode": PERIODE_1AN, "per_max": 0.9, "epoque": True}
        epoque=True : seuls les comptes publiés avant la date d'achat sont utilisés (honnête)."""
        self.mode, self.cours, self.comptes = mode, cours, comptes
        self.financieres, self.note_min, self.valo = financieres, note_min, valo
        self.memo = {}  # la note ne change qu'à chaque publication de comptes : on la mémorise

    def note(self, ticker, date):
        if self.mode == MODE_SANS_NOTE:
            return None
        if ticker not in self.comptes:
            return None
        serie = self.cours[ticker].dropna()
        if self.mode == MODE_AUJOURDHUI:
            cle = (ticker, "aujourd'hui")
            if cle not in self.memo:
                self.memo[cle] = analyse_fondamentale(self.comptes[ticker], serie,
                                                      ticker in self.financieres)["note"]
            return self.memo[cle]
        comptes_date = comptes_a_la_date(self.comptes[ticker], date)
        cle = (ticker, sum(len(v) for v in comptes_date.values()))
        if cle not in self.memo:
            self.memo[cle] = analyse_fondamentale(comptes_date, serie.loc[:date],
                                                  ticker in self.financieres)["note"]
        return self.memo[cle]

    def valeurs(self, ticker, date):
        """Croissance du CA et ratio PER de l'action à la date donnée (None si indisponibles)."""
        if not self.valo or ticker not in self.comptes:
            return None
        serie = self.cours[ticker].dropna().loc[:date]  # cours connus à la date (le PER dépend du cours du jour)
        if self.valo["epoque"]:
            comptes = comptes_a_la_date(self.comptes[ticker], date)
        else:
            comptes = self.comptes[ticker]
        return valorisation(comptes, serie)

    def infos(self, ticker, date):
        """Valeurs enregistrées avec chaque achat (affichées dans le tableau des transactions)."""
        infos = {"note": self.note(ticker, date)}
        v = self.valeurs(ticker, date)
        if v is not None:
            infos["ca_achat"] = v["ca_1an"] if self.valo["periode"] == PERIODE_1AN else v["ca_3ans"]
            infos["ratio_achat"] = v["ratio"]
        return infos

    def autorise(self, ticker, date):
        # 1. Note fondamentale (si ce filtre est choisi)
        if self.mode != MODE_SANS_NOTE:
            n = self.note(ticker, date)
            if n is None or n < self.note_min:
                return False
        # 2. Croissance du CA et ratio PER (si ces filtres sont activés)
        if self.valo:
            v = self.valeurs(ticker, date)
            if v is None or v["probleme"] or v["ratio"] is None:
                return False  # données manquantes, PER négatif, > 100 ou anormal : pas d'achat
            croissance = v["ca_1an"] if self.valo["periode"] == PERIODE_1AN else v["ca_3ans"]
            if croissance is None or croissance < self.valo["ca_min"] or v["ratio"] > self.valo["per_max"] + 1e-9:
                return False
        return True


def rsi_fiable(serie, semaines_ignorees=30):
    """RSI, sauf pendant les 30 premières semaines de cotation : sans assez d'historique,
    le RSI d'une action tout juste introduite en bourse peut valoir 0 et donner un faux signal d'achat."""
    r = rsi(serie)
    r.iloc[:semaines_ignorees] = float("nan")
    return r


def simuler_portefeuille(cours, tickers, filtre, debut, capital, mise, seuil_achat, seuil_vente, indice=None):
    """Simulation semaine par semaine. Renvoie (transactions, évolution du portefeuille).

    Si `indice` est fourni (cours de l'indice), l'argent en attente d'un achat est placé dans
    l'indice (comme un ETF) : il monte et baisse avec lui, et on le reprend pour chaque achat."""
    prix = cours[tickers].ffill()  # semaine sans cotation : on garde le dernier cours connu
    # RSI calculé sur tout l'historique (pour qu'il soit déjà fiable à la date de départ)
    rsis = pd.DataFrame({t: rsi_fiable(cours[t].dropna()) for t in tickers}).reindex(prix.index)
    dates = prix.index[prix.index >= debut]
    tableau_prix, tableau_rsi = prix.loc[dates].to_numpy(), rsis.loc[dates].to_numpy()

    cours_indice = indice.reindex(dates).ffill().to_numpy() if indice is not None else None
    liquidites, positions, transactions, evolution = capital, {}, [], []
    for i, date in enumerate(dates):
        # 0. L'argent en attente suit l'indice (si l'option est choisie)
        if cours_indice is not None and i > 0 and cours_indice[i - 1] > 0 and cours_indice[i] > 0:
            liquidites *= cours_indice[i] / cours_indice[i - 1]
        # 1. Ventes : actions détenues dont le RSI dépasse le seuil de surachat
        for j in list(positions):
            if tableau_rsi[i, j] > seuil_vente:
                pos = positions.pop(j)
                montant_vente = pos["parts"] * tableau_prix[i, j]
                liquidites += montant_vente
                transactions.append({**pos, "date_vente": date, "prix_vente": tableau_prix[i, j],
                                     "montant_vente": montant_vente, "statut": "Vendue",
                                     "raison": f"RSI > {seuil_vente}"})
        # 2. Achats : les plus survendues d'abord, tant qu'il reste de l'argent
        candidats = [(tableau_rsi[i, j], j) for j in range(len(tickers))
                     if j not in positions and tableau_rsi[i, j] < seuil_achat and tableau_prix[i, j] > 0]
        for r, j in sorted(candidats):
            if liquidites < ACHAT_MINIMUM:
                break
            if not filtre.autorise(tickers[j], date):
                continue
            montant = min(mise, liquidites)
            liquidites -= montant
            positions[j] = {"Ticker": tickers[j], "date": date, "prix": tableau_prix[i, j], "rsi": r,
                            "parts": montant / tableau_prix[i, j], "montant": montant,
                            **filtre.infos(tickers[j], date)}
        # 3. Valeur du portefeuille cette semaine
        investi = sum(p["parts"] * tableau_prix[i, j] for j, p in positions.items())
        evolution.append({"date": date, "Portefeuille": liquidites + investi, "Liquidités": liquidites})

    for j, pos in positions.items():  # positions encore ouvertes, valorisées au dernier cours
        montant_vente = pos["parts"] * tableau_prix[-1, j]
        transactions.append({**pos, "date_vente": dates[-1], "prix_vente": tableau_prix[-1, j],
                             "montant_vente": montant_vente, "statut": "En cours", "raison": "—"})
    return transactions, pd.DataFrame(evolution).set_index("date")


# -----------------------------------------------------------------------------
# Stratégie « Zone Fibonacci + invalidation + objectif » (méthode Elliott / Fibonacci)
# -----------------------------------------------------------------------------
# - Dernière hausse = creux A → sommet B, repérés par le ZigZag avec les SEULS cours connus à chaque date.
# - ACHAT  quand le cours revient dans la zone de retracement (ex. 50 % à 78,6 % de la hausse),
#          et (option) qu'il reste au-dessus de la moyenne 200 semaines.
# - VENTE  à l'objectif : A + extension × (B − A)   (ex. 1,618)
#          ou si le scénario est invalidé : clôture sous le niveau d'invalidation (ex. sous le creux A).

STRAT_RSI = "RSI (survente / surachat)"
STRAT_FIBO = "Zone Fibonacci + invalidation + objectif"


def jambes_en_ligne(valeurs, seuil):
    """Pour chaque semaine, la dernière hausse (creux A, sommet B) connue À CETTE DATE (sans regarder le futur).

    Pendant une hausse, le sommet B est provisoire (le plus haut atteint) ; pendant une baisse,
    on garde la dernière hausse terminée. Renvoie deux tableaux A et B (NaN si inconnue)."""
    n = len(valeurs)
    A, B = np.full(n, np.nan), np.full(n, np.nan)
    tendance, i_haut, i_bas, i_ext = None, 0, 0, 0
    dernier_creux, hausse_terminee = None, None
    for i in range(1, n):
        v = valeurs[i]
        if tendance is None:  # démarrage : on attend un premier mouvement suffisant
            i_haut = i if v > valeurs[i_haut] else i_haut
            i_bas = i if v < valeurs[i_bas] else i_bas
            if v >= valeurs[i_bas] * (1 + seuil):
                dernier_creux, tendance, i_ext = valeurs[i_bas], "hausse", i
            elif v <= valeurs[i_haut] * (1 - seuil):
                tendance, i_ext = "baisse", i
        elif tendance == "hausse":
            if v > valeurs[i_ext]:
                i_ext = i
            elif v <= valeurs[i_ext] * (1 - seuil):  # le sommet est confirmé : la hausse est terminée
                hausse_terminee = (dernier_creux, valeurs[i_ext]) if dernier_creux is not None else None
                tendance, i_ext = "baisse", i
        else:
            if v < valeurs[i_ext]:
                i_ext = i
            elif v >= valeurs[i_ext] * (1 + seuil):  # le creux est confirmé
                dernier_creux, tendance, i_ext = valeurs[i_ext], "hausse", i
        if tendance == "hausse" and dernier_creux is not None:
            A[i], B[i] = dernier_creux, valeurs[i_ext]
        elif tendance == "baisse" and hausse_terminee:
            A[i], B[i] = hausse_terminee
    return A, B


def simuler_portefeuille_fibo(cours, tickers, filtre, debut, capital, mise, zone_haut, zone_bas,
                              invalidation, extension, filtre_200, indice=None, seuil_zigzag=SEUIL_ZIGZAG):
    """Simulation semaine par semaine de la stratégie Fibonacci. Même format de sortie que simuler_portefeuille.

    zone_haut / zone_bas : retracements délimitant la zone d'achat (ex. 0,5 et 0,786)
    invalidation         : retracement sous lequel on vend (1,0 = sous le creux A)
    extension            : objectif de vente = A + extension × (B − A) (ex. 1,618)"""
    prix = cours[tickers].ffill()
    dates = prix.index[prix.index >= debut]
    # Dernière hausse connue à chaque date, pour chaque action
    tableau_a = pd.DataFrame(index=prix.index, columns=tickers, dtype=float)
    tableau_b = tableau_a.copy()
    for t in tickers:
        serie = cours[t].dropna()
        if len(serie) > 30:
            a, b = jambes_en_ligne(serie.values, seuil_zigzag)
            tableau_a.loc[serie.index, t], tableau_b.loc[serie.index, t] = a, b
    A = tableau_a.ffill(limit=2).loc[dates].to_numpy()
    B = tableau_b.ffill(limit=2).loc[dates].to_numpy()
    P = prix.loc[dates].to_numpy()
    W = prix.rolling(PERIODE_WMA).mean().loc[dates].to_numpy()  # moyenne 200 semaines
    R = pd.DataFrame({t: rsi_fiable(cours[t].dropna()) for t in tickers}).reindex(prix.index).loc[dates].to_numpy()

    cours_indice = indice.reindex(dates).ffill().to_numpy() if indice is not None else None
    liquidites, positions, transactions, evolution = capital, {}, [], []
    for i, date in enumerate(dates):
        if cours_indice is not None and i > 0 and cours_indice[i - 1] > 0 and cours_indice[i] > 0:
            liquidites *= cours_indice[i] / cours_indice[i - 1]  # l'argent en attente suit l'indice
        # 1. Ventes : objectif atteint, ou scénario invalidé
        for j in list(positions):
            pos, px = positions[j], P[i, j]
            if np.isnan(px):
                continue
            raison = None
            if px < pos["stop"]:
                raison = "Invalidation"
            elif px >= pos["objectif"]:
                raison = "Objectif atteint"
            if raison:
                positions.pop(j)
                montant_vente = pos["parts"] * px
                liquidites += montant_vente
                transactions.append({**pos, "date_vente": date, "prix_vente": px,
                                     "montant_vente": montant_vente, "statut": "Vendue", "raison": raison})
        # 2. Achats : actions revenues dans la zone (les plus survendues d'abord)
        candidats = []
        for j in range(len(tickers)):
            if j in positions or np.isnan(P[i, j]) or np.isnan(A[i, j]) or not B[i, j] > A[i, j]:
                continue
            repli = (B[i, j] - P[i, j]) / (B[i, j] - A[i, j])  # 0 = au sommet B, 1 = revenu au creux A
            if not zone_haut <= repli <= zone_bas:
                continue
            if filtre_200 and not P[i, j] > W[i, j]:
                continue
            candidats.append((R[i, j] if not np.isnan(R[i, j]) else 50, j, repli))
        for r, j, repli in sorted(candidats):
            if liquidites < ACHAT_MINIMUM:
                break
            if not filtre.autorise(tickers[j], date):
                continue
            montant = min(mise, liquidites)
            liquidites -= montant
            a, b = A[i, j], B[i, j]
            positions[j] = {"Ticker": tickers[j], "date": date, "prix": P[i, j], "rsi": r, "repli": repli * 100,
                            "parts": montant / P[i, j], "montant": montant, **filtre.infos(tickers[j], date),
                            "stop": b - invalidation * (b - a), "objectif": a + extension * (b - a)}
        investi = sum(p["parts"] * (P[i, j] if not np.isnan(P[i, j]) else p["prix"]) for j, p in positions.items())
        evolution.append({"date": date, "Portefeuille": liquidites + investi, "Liquidités": liquidites})

    for j, pos in positions.items():
        montant_vente = pos["parts"] * P[-1, j]
        transactions.append({**pos, "date_vente": dates[-1], "prix_vente": P[-1, j],
                             "montant_vente": montant_vente, "statut": "En cours", "raison": "—"})
    return transactions, pd.DataFrame(evolution).set_index("date")


def reference_equiponderee(cours, tickers, debut, capital):
    """Référence « honnête » : le capital réparti à parts égales, à la date de départ, entre toutes
    les actions ACTUELLES de l'indice, puis gardées. Elle a le même biais que le test (seules les
    entreprises encore dans l'indice aujourd'hui), ce qui permet une comparaison juste."""
    prix = cours[tickers].ffill().loc[debut:]
    prix = prix.loc[:, prix.iloc[0].notna()]  # actions déjà cotées à la date de départ
    if prix.empty:
        return None
    return capital * (prix / prix.iloc[0]).mean(axis=1)


def graphique_evolution(evolution, capital, indice, nom_indice, reference=None, attente_indice=False):
    """Évolution de la valeur du portefeuille, comparée à l'indice, à la référence et au capital de départ."""
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=evolution.index, y=evolution["Portefeuille"], name="Portefeuille",
                             line=dict(color="#1f77b4", width=3)))
    if indice is not None:
        fig.add_trace(go.Scatter(x=indice.index, y=indice.values, name=f"{nom_indice} (même capital)",
                                 line=dict(color="#ff7f0e", width=2)))
    if reference is not None:
        fig.add_trace(go.Scatter(x=reference.index, y=reference.values, name="Référence équipondérée",
                                 line=dict(color="#2ca02c", width=2, dash="dash")))
    nom_attente = "Dont argent en attente (placé dans l'indice)" if attente_indice else "Dont liquidités"
    fig.add_trace(go.Scatter(x=evolution.index, y=evolution["Liquidités"], name=nom_attente,
                             line=dict(color="gray", width=1, dash="dot")))
    fig.add_hline(y=capital, line=dict(color="black", width=1, dash="dash"),
                  annotation_text=f"Départ {capital:,.0f} €".replace(",", " "))
    fig.update_layout(title="Évolution du portefeuille (€)", height=420, hovermode="x unified",
                      margin=dict(l=10, r=10, t=40, b=10), legend=dict(orientation="h", y=-0.15))
    st.plotly_chart(fig, width="stretch", config=SANS_OUTILS)


def graphique_transactions(ticker, serie, transactions, seuil_achat, seuil_vente, debut):
    """Cours avec les achats (▲ vert) et les ventes (▼ rouge). Stratégie RSI : graphique du RSI en dessous.
    Stratégie Fibonacci (seuil_achat = None) : objectif et invalidation de chaque achat en pointillés."""
    serie = serie.loc[debut - pd.Timedelta(weeks=26):]
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=serie.index, y=serie.values, name="Cours", line=dict(color="#1f77b4")))
    fig.add_trace(go.Scatter(x=[t["date"] for t in transactions], y=[t["prix"] for t in transactions],
                             mode="markers", name="Achat",
                             marker=dict(symbol="triangle-up", size=13, color="green")))
    ventes = [t for t in transactions if t["statut"] == "Vendue"]
    fig.add_trace(go.Scatter(x=[t["date_vente"] for t in ventes], y=[t["prix_vente"] for t in ventes],
                             mode="markers", name="Vente",
                             marker=dict(symbol="triangle-down", size=13, color="red")))
    for k, t in enumerate(transactions):  # stratégie Fibonacci : objectif et invalidation de chaque achat
        if "objectif" in t and "stop" in t:
            for niveau, couleur, nom in [(t["objectif"], "green", "Objectif"), (t["stop"], "red", "Invalidation")]:
                fig.add_trace(go.Scatter(x=[t["date"], t["date_vente"]], y=[niveau, niveau], mode="lines",
                                         name=nom, legendgroup=nom, showlegend=(k == 0),
                                         line=dict(color=couleur, width=1, dash="dot")))
    fig.update_layout(title=f"{ticker} — achats et ventes", height=380, hovermode="x unified",
                      margin=dict(l=10, r=10, t=40, b=10), legend=dict(orientation="h", y=-0.15))
    st.plotly_chart(fig, width="stretch", config=SANS_OUTILS)
    if seuil_achat is None:
        return

    r = rsi(serie)
    fig_rsi = go.Figure(go.Scatter(x=r.index, y=r.values, name="RSI", line=dict(color="#9467bd")))
    fig_rsi.add_hline(y=seuil_vente, line=dict(color="red", dash="dot"), annotation_text=f"Vente > {seuil_vente}")
    fig_rsi.add_hline(y=seuil_achat, line=dict(color="green", dash="dot"), annotation_text=f"Achat < {seuil_achat}")
    fig_rsi.update_layout(title="RSI hebdomadaire", height=220, yaxis=dict(range=[0, 100]),
                          margin=dict(l=10, r=10, t=40, b=10))
    st.plotly_chart(fig_rsi, width="stretch", config=SANS_OUTILS)


def euros(x):
    return f"{x:,.0f} €".replace(",", " ")


def page_test_historique():
    st.title("🧪 Test historique")
    st.caption("Simulation d'un portefeuille, semaine après semaine, selon la stratégie choisie.")

    nom_indice = st.radio("Indice", ["CAC 40", "Nasdaq 100", "S&P 500"], horizontal=True, key="bt_indice")
    strategie = st.radio("Stratégie", [STRAT_RSI, STRAT_FIBO], key="bt_strategie",
                         help="RSI : achat en survente, vente en surachat. Fibonacci : achat quand le cours revient "
                              "dans la zone de retracement de la dernière hausse, vente à l'objectif d'extension "
                              "ou si le scénario est invalidé.")
    mode = st.radio("Filtre fondamental", [MODE_SANS_NOTE, MODE_EPOQUE, MODE_AUJOURDHUI], key="bt_mode",
                    help="« Aucune note » : aucun filtre sur la santé financière. « Époque » : seulement les comptes publiés "
                         "avant l'achat. « Aujourd'hui » : note actuelle appliquée au passé (trop flatteur).")
    with st.expander("⚙️ Règles", expanded=False):
        c1, c2 = st.columns(2)
        capital = c1.number_input("Capital de départ (€)", 1000, 1_000_000, 10_000, 1000, key="bt_capital")
        mise = c2.number_input("Achat maximum par ligne (€)", 100, 100_000, 1_000, 100, key="bt_mise")
        debut = pd.Timestamp(st.date_input("Date de départ", pd.Timestamp("2023-01-01"), key="bt_debut",
                                           format="DD/MM/YYYY"))
        # Réglages par défaut issus de l'analyse sur 4 périodes × 3 indices (2011-2026) :
        # acheter un peu plus tôt (35) et revendre plus tard (80) a donné de meilleurs résultats que 30/70.
        if strategie == STRAT_RSI:
            seuil_achat = st.slider("Achat si RSI hebdo inférieur à", 15, 50, 35, key="bt_achat")
            seuil_vente = st.slider("Vente si RSI hebdo supérieur à", 50, 90, 80, key="bt_vente")
        else:
            # Réglages par défaut issus de l'analyse (zone 0,5-0,786, invalidation sous A, objectif 1,618)
            seuil_achat = seuil_vente = None
            niveaux = [0.236, 0.382, 0.5, 0.618, 0.786]
            zone_haut, zone_bas = st.select_slider(
                "Zone d'achat (repli de la dernière hausse)", options=niveaux, value=(0.5, 0.786),
                format_func=lambda x: f"{x * 100:.1f} %".replace(".0 %", " %"), key="bt_zone")
            invalidation = st.select_slider(
                "Invalidation (vente si le repli dépasse)", options=[0.786, 0.886, 1.0, 1.1], value=1.0,
                format_func=lambda x: "sous le creux A (100 %)" if x == 1.0 else f"{x * 100:.1f} %", key="bt_inval")
            extension = st.select_slider(
                "Objectif de vente (extension de la hausse)", options=[1.0, 1.272, 1.618, 2.0, 2.618], value=1.618,
                format_func=lambda x: "retour au sommet B (1,0)" if x == 1.0 else f"{x:g}".replace(".", ","),
                key="bt_ext")
            filtre_200 = st.toggle("Seulement si le cours est au-dessus de la moyenne 200 semaines", value=True,
                                   key="bt_f200", help="Tendance de fond haussière. Moyenne disponible seulement "
                                                       "après 200 semaines de cotation (≈ fin 2020 pour 10 ans de données).")
        attente_indice = st.toggle("Placer l'argent en attente dans l'indice (ETF)", value=True, key="bt_etf",
                                   help="Au lieu de dormir, l'argent qui attend un signal d'achat suit l'indice. "
                                        "C'est l'amélioration la plus fiable trouvée par l'analyse.")
        note_min = st.slider("Note fondamentale minimale (si filtre)", 0.0, 10.0, 7.0, 0.5, key="bt_note")

    # Filtres de valorisation, comme l'écran Opportunités (valeurs par défaut = derniers réglages de cet écran)
    with st.expander("🎛️ Filtres croissance du CA / PER (comme Opportunités)", expanded=False):
        valo_actif = st.toggle("Activer ces filtres à l'achat", value=False, key="bt_valo")
        def defaut(param, typ, valeur):
            try:
                return typ(st.query_params.get(param, valeur))
            except ValueError:
                return valeur
        c1, c2 = st.columns([2, 1], vertical_alignment="bottom")
        bt_ca_min = c1.slider("Croissance du CA minimum (%)", -10, 30,
                              min(30, max(-10, defaut("ca_min", int, 5))), step=1, key="bt_ca_min", format="%+d %%")
        periodes = [PERIODE_1AN, PERIODE_3ANS]
        p0 = defaut("ca_periode", str, PERIODE_1AN)
        bt_periode = c2.selectbox("Période", periodes, index=periodes.index(p0) if p0 in periodes else 0,
                                  key="bt_ca_periode")
        bt_per_max = st.slider("Ratio PER actuel / PER moyen maximum", 0.5, 1.5,
                               min(1.5, max(0.5, round(defaut("per_max", float, 0.9) * 20) / 20)), step=0.05,
                               key="bt_per_max", format="%.2f")
        st.caption("< 1 : moins cher que d'habitude · > 1 : plus cher que d'habitude. "
                   "Les PER négatifs, supérieurs à 100 ou anormaux (< 3) sont exclus.")
        valo_epoque = st.radio("Comptes utilisés", ["Ceux publiés avant l'achat (honnête)",
                                                    "Ceux d'aujourd'hui (trop optimiste)"],
                               key="bt_valo_mode").startswith("Ceux publiés")
        st.caption("⚠️ Yahoo ne fournit que 4 exercices de comptes (2022 à 2025 en général). Avec les comptes "
                   "publiés avant l'achat, ces filtres ne deviennent utilisables qu'à partir d'avril 2024 environ "
                   "(croissance sur 1 an et ratio PER), et d'avril 2026 pour la moyenne sur 3 ans : "
                   "avant, aucune action ne peut être achetée.")
    valo = ({"ca_min": bt_ca_min, "periode": bt_periode, "per_max": bt_per_max, "epoque": valo_epoque}
            if valo_actif else None)

    regle_note = "" if mode == MODE_SANS_NOTE else f" et note fondamentale ≥ {note_min:g}/10"
    if valo:
        regle_note += (f", croissance du CA ({bt_periode.lower()}) ≥ {bt_ca_min:+d} % et ratio PER ≤ "
                       f"{bt_per_max:.2f}".replace(".", ","))
    texte_attente = " L'argent en attente est placé dans l'indice." if attente_indice else ""
    if strategie == STRAT_RSI:
        texte_regles = f"Achat si RSI < {seuil_achat}{regle_note} ; vente si RSI > {seuil_vente}."
    else:
        def fr(x):  # 0.786 -> « 78,6 % »
            return f"{x * 100:.1f}".rstrip("0").rstrip(".").replace(".", ",") + " %"
        texte_inval = "sous le creux A" if invalidation == 1.0 else f"au-delà de {fr(invalidation)} de repli"
        texte_regles = (f"Achat si le cours revient entre {fr(zone_haut)} et {fr(zone_bas)} de repli de la dernière "
                        f"hausse{' (au-dessus de la 200 WMA)' if filtre_200 else ''}{regle_note} ; vente à l'objectif "
                        f"{f'{extension:g}'.replace('.', ',')} ou si le cours passe {texte_inval}.")
    st.caption(f"Départ le {debut:%d/%m/%Y} avec {euros(capital)}, {euros(mise)} maximum par achat. "
               f"{texte_regles}{texte_attente}")

    if not st.toggle("Lancer le test", key=f"bt_lancer_{nom_indice}"):
        return

    with st.spinner("Téléchargement des cours…"):
        noms, financieres = composants_indice(nom_indice)
        cours = cours_hebdo(tuple(sorted(noms)))
        indice_brut = cours_hebdo((INDICES_YAHOO[nom_indice],))
    if cours.empty:
        st.error("Impossible de récupérer les cours. Réessayez plus tard.")
        return
    if debut >= cours.index[-1]:
        st.error("La date de départ doit être dans le passé.")
        return
    tickers = [t for t in noms if t in cours.columns and cours[t].notna().sum() > 30]

    # Comptes annuels : seulement si un filtre fondamental est utilisé (et seulement pour
    # les actions qui ont été au moins une fois en survente depuis la date de départ)
    comptes = {}
    if mode != MODE_SANS_NOTE or valo:
        if strategie == STRAT_RSI:
            candidats = [t for t in tickers if (rsi_fiable(cours[t].dropna()).loc[debut:] < seuil_achat).any()]
        else:
            candidats = tickers  # toutes les actions peuvent entrer dans leur zone d'achat
        comptes, erreurs = comptes_annuels(candidats)
        if erreurs:
            st.warning(f"Comptes indisponibles pour {len(erreurs)} action(s) : elles ne seront pas achetées. "
                       "Patientez quelques minutes puis appuyez sur « Réessayer ».")
            if st.button("🔄 Réessayer", key="bt_reessayer"):
                st.rerun()

    # Cours de l'indice, alignés sur les semaines des actions
    cours_indice = None
    if not indice_brut.empty:
        cours_indice = indice_brut.iloc[:, 0].dropna().reindex(cours.index, method="ffill")
    if attente_indice and cours_indice is None:
        st.warning("Cours de l'indice indisponibles : l'argent en attente reste en liquidités.")

    filtre = FiltreFondamental(mode, cours, comptes, financieres, note_min, valo)
    if strategie == STRAT_RSI:
        transactions, evolution = simuler_portefeuille(cours, tickers, filtre, debut, capital, mise,
                                                       seuil_achat, seuil_vente,
                                                       indice=cours_indice if attente_indice else None)
    else:
        with st.spinner("Simulation de la stratégie Fibonacci…"):
            transactions, evolution = simuler_portefeuille_fibo(
                cours, tickers, filtre, debut, capital, mise, zone_haut, zone_bas, invalidation, extension,
                filtre_200, indice=cours_indice if attente_indice else None)

    # Comparaisons : même capital placé dans l'indice, et référence équipondérée
    indice = None
    if cours_indice is not None:
        serie_indice = cours_indice.loc[debut:].dropna()
        if not serie_indice.empty:
            indice = capital * serie_indice / serie_indice.iloc[0]
    reference = reference_equiponderee(cours, tickers, debut, capital)

    # --- Résumé ---
    final = evolution["Portefeuille"].iloc[-1]
    gain = final - capital
    plus_haut = evolution["Portefeuille"].cummax()
    pire_baisse = ((evolution["Portefeuille"] / plus_haut - 1).min()) * 100
    st.subheader("📊 Résultats")
    c1, c2 = st.columns(2)
    c1.metric("Valeur finale", euros(final), f"{gain / capital:+.1%}")
    c2.metric(f"{nom_indice} (même capital)", euros(indice.iloc[-1]) if indice is not None else "—",
              f"{indice.iloc[-1] / capital - 1:+.1%}" if indice is not None else None)
    c3, c4 = st.columns(2)
    c3.metric("Référence équipondérée", euros(reference.iloc[-1]) if reference is not None else "—",
              f"{reference.iloc[-1] / capital - 1:+.1%}" if reference is not None else None,
              help="Toutes les actions actuelles de l'indice achetées à parts égales au départ, puis gardées")
    c4.metric("Pire baisse en cours de route", f"{pire_baisse:.1f} %",
              help="Plus forte chute de la valeur du portefeuille depuis un sommet")

    if reference is not None:
        ecart = final - reference.iloc[-1]
        if ecart >= 0:
            st.success(f"✅ La stratégie fait mieux que la référence équipondérée de {euros(ecart)}.")
        else:
            st.warning(f"⚠️ La stratégie fait moins bien que la référence équipondérée de {euros(-ecart)} : "
                       "acheter simplement toutes les actions de l'indice aurait rapporté plus.")

    graphique_evolution(evolution, capital, indice, nom_indice, reference, attente_indice)
    with st.expander("ℹ️ Comment lire ces comparaisons"):
        st.markdown(
            "- **Biais du survivant** : le test utilise la liste ACTUELLE des actions de l'indice. "
            "Les entreprises qui ont chuté au point de sortir de l'indice (ou fait faillite) n'y sont pas. "
            "Les résultats sont donc trop flatteurs, surtout quand on garde longtemps les actions.\n"
            "- **Référence équipondérée** (vert) : elle a exactement le même biais. C'est donc la "
            "comparaison la plus juste : si la stratégie ne la bat pas, sa méthode n'apporte rien de plus "
            "que de détenir toutes les actions de l'indice.\n"
            "- **Indice** (orange) : ce que vous auriez réellement eu avec un ETF (hors dividendes)."
        )
    st.caption("L'indice est sans les dividendes, alors que les actions du portefeuille les incluent. "
               "Les montants des actions américaines sont en dollars, comptés comme des euros. "
               "Frais de courtage et impôts non compris.")
    if mode == MODE_AUJOURDHUI:
        st.warning("⚠️ Résultat trop optimiste : les entreprises sont choisies avec leur note d'aujourd'hui, "
                   "c'est-à-dire en sachant déjà qu'elles se portent bien.")

    if not transactions:
        conseil = ("Avec les filtres croissance / PER sur les comptes publiés avant l'achat, aucun achat n'est "
                   "possible avant avril 2024 environ (avril 2026 pour la moyenne 3 ans). "
                   if valo and valo["epoque"] else "")
        st.info(f"Aucun achat sur la période. {conseil}Essayez des réglages moins stricts "
                "(seuil d'achat plus haut, zone d'achat plus large, filtres plus souples).")
        return

    df = pd.DataFrame(transactions)
    df["Nom"] = df["Ticker"].map(noms)
    df["Rendement %"] = (df["prix_vente"] / df["prix"] - 1) * 100
    df["Gain €"] = df["montant_vente"] - df["montant"]
    df["Durée (sem.)"] = ((df["date_vente"] - df["date"]).dt.days / 7).round().astype(int)

    c5, c6, c7 = st.columns(3)
    c5.metric("Achats", len(df))
    c6.metric("Gagnants", f"{(df['Rendement %'] > 0).mean():.0%}")
    c7.metric("En cours", int((df["statut"] == "En cours").sum()))
    if strategie == STRAT_FIBO:
        c8, c9 = st.columns(2)
        c8.metric("🎯 Objectifs atteints", int((df["raison"] == "Objectif atteint").sum()))
        c9.metric("🛑 Invalidations", int((df["raison"] == "Invalidation").sum()))

    # --- Tableaux ---
    prix = st.column_config.NumberColumn(format="%.2f")
    pct = st.column_config.NumberColumn(format="%+.1f %%")
    eur = st.column_config.NumberColumn(format="%.0f €")
    st.markdown("**Toutes les transactions**")
    detail = df.sort_values("date", ascending=False).rename(columns={
        "date": "Achat le", "prix": "Prix achat", "montant": "Investi", "date_vente": "Vente le",
        "prix_vente": "Prix vente", "statut": "Statut", "note": "Note fond.", "rsi": "RSI achat",
        "raison": "Raison", "repli": "Repli à l'achat %", "objectif": "Objectif", "stop": "Invalidation",
        "ca_achat": "Croissance CA à l'achat %", "ratio_achat": "Ratio PER à l'achat"})
    colonnes = ["Ticker", "Nom", "Achat le", "Investi", "Gain €", "Rendement %", "Vente le", "Statut", "Raison",
                "Durée (sem.)", "Prix achat", "Prix vente"]
    colonnes += ["RSI achat"] if strategie == STRAT_RSI else ["Repli à l'achat %", "Objectif", "Invalidation"]
    if mode != MODE_SANS_NOTE:
        colonnes.append("Note fond.")
    if valo:
        colonnes += ["Croissance CA à l'achat %", "Ratio PER à l'achat"]
    st.dataframe(detail[colonnes], hide_index=True, width="stretch", column_config={
        "Ticker": st.column_config.TextColumn(pinned=True),
        "Nom": st.column_config.TextColumn(width="medium"),
        "Achat le": st.column_config.DateColumn(format="DD/MM/YYYY"),
        "Vente le": st.column_config.DateColumn(format="DD/MM/YYYY"),
        "Investi": eur, "Gain €": st.column_config.NumberColumn(format="%+.0f €"),
        "Prix achat": prix, "Prix vente": prix, "Rendement %": pct,
        "Note fond.": st.column_config.NumberColumn(format="%.1f"),
        "RSI achat": st.column_config.NumberColumn(format="%.0f"),
        "Repli à l'achat %": st.column_config.NumberColumn(format="%.0f %%"),
        "Objectif": prix, "Invalidation": prix,
        "Croissance CA à l'achat %": st.column_config.NumberColumn(format="%+.1f %%"),
        "Ratio PER à l'achat": st.column_config.NumberColumn(format="%.2f"),
    })

    st.markdown("**Gain par action**")
    par_action = (df.groupby(["Ticker", "Nom"])
                  .agg(Achats=("Gain €", "size"), Investi=("montant", "sum"), Gain=("Gain €", "sum"))
                  .reset_index().sort_values("Gain", ascending=False))
    st.dataframe(par_action, hide_index=True, width="stretch", column_config={
        "Ticker": st.column_config.TextColumn(pinned=True),
        "Nom": st.column_config.TextColumn(width="medium"),
        "Investi": eur, "Gain": st.column_config.NumberColumn("Gain €", format="%+.0f €")})

    # --- Graphique d'une action ---
    st.divider()
    choix = st.selectbox("Voir les achats et ventes de", par_action["Ticker"],
                         format_func=lambda t: f"{t} — {noms.get(t, t)}", key="bt_choix")
    graphique_transactions(choix, cours[choix].dropna(), [tr for tr in transactions if tr["Ticker"] == choix],
                           seuil_achat, seuil_vente, debut)
    st.caption("Les performances passées ne préjugent pas des performances futures.")


# =============================================================================
# 13. NAVIGATION ENTRE LES PAGES
# =============================================================================
# Des boutons en haut de page plutôt qu'un menu latéral : plus pratique sur iPhone.
page = st.radio("Page", ["🎯 Opportunités", "🚨 Alerte achat", "🧪 Test historique"], horizontal=True,
                label_visibility="collapsed", key="page")
if page == "🎯 Opportunités":
    main()
elif page == "🚨 Alerte achat":
    page_alerte_achat()
else:
    page_test_historique()
st.caption("⚠️ Outil d'aide à la réflexion, pas un conseil en investissement. Données : Yahoo Finance.")
