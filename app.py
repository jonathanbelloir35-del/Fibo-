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


def main():
    st.title("🎯 Opportunités")
    st.caption("Note technique (200 WMA, Fibonacci, RSI, rebond) et note fondamentale "
               "(chiffre d'affaires, rentabilité, free cash flow, dette, PER), chacune sur 10.")

    nom_indice = st.radio("Indice", ["CAC 40", "Nasdaq 100", "S&P 500"], horizontal=True)

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

    # --- Note fondamentale : seulement pour les meilleures notes techniques (Yahoo limite les requêtes) ---
    tableau = tableau.sort_values("Note technique", ascending=False, na_position="last")
    nb_max = len(tableau)
    nb_defaut = min(nb_max, 40)
    with st.expander("⚙️ Notes fondamentales", expanded=False):
        st.caption("Les comptes annuels sont téléchargés action par action, ce qui est lent. "
                   "On commence par les meilleures notes techniques ; augmentez le nombre si besoin "
                   "(ce qui a déjà été téléchargé est gardé 24 h).")
        nb = st.slider("Nombre d'actions à analyser", 0, nb_max, nb_defaut, step=5 if nb_max > 50 else 1,
                       key=f"nb_{nom_indice}")
    a_analyser = list(tableau["Ticker"].head(nb))
    comptes, erreurs = comptes_annuels(a_analyser)

    notes_fond, croissances, pers, dettes = [], [], [], []
    for ticker in tableau["Ticker"]:
        if ticker in comptes:
            f = analyse_fondamentale(comptes[ticker], cours[ticker].dropna(), ticker in financieres)
            ch = f["chiffres"]
            notes_fond.append(f["note"])
            croissances.append(ch.get("croissance_ca"))
            pers.append(ch.get("per"))
            dettes.append(ch.get("dette_ebitda"))
        else:
            notes_fond.append(None)
            croissances.append(None)
            pers.append(None)
            dettes.append(None)
    tableau["Note fondamentale"] = pd.to_numeric(pd.Series(notes_fond, index=tableau.index), errors="coerce")
    tableau["Croissance CA %/an"] = pd.to_numeric(pd.Series(croissances, index=tableau.index), errors="coerce")
    tableau["PER"] = pd.to_numeric(pd.Series(pers, index=tableau.index), errors="coerce")
    tableau["Dette/EBITDA"] = pd.to_numeric(pd.Series(dettes, index=tableau.index), errors="coerce")
    tableau["Verdict"] = [verdict(nt, nf) for nt, nf in zip(tableau["Note technique"], tableau["Note fondamentale"])]

    if erreurs:
        st.warning(f"Comptes indisponibles pour {len(erreurs)} action(s) : Yahoo limite sans doute les requêtes. "
                   "Patientez quelques minutes puis appuyez sur « Réessayer ».")
        if st.button("🔄 Réessayer"):
            st.rerun()

    # --- Tri : les actions avec les deux notes, de la meilleure moyenne à la moins bonne ---
    tableau["_moyenne"] = tableau[["Note technique", "Note fondamentale"]].mean(axis=1, skipna=False)
    tableau = tableau.sort_values(["_moyenne", "Note technique"], ascending=False, na_position="last")

    c1, c2, c3 = st.columns(3)
    c1.metric("Actions analysées", len(tableau))
    c2.metric("🎯 Opportunités", int((tableau["Verdict"] == "🎯 Opportunité").sum()))
    c3.metric("Notes fondamentales", int(tableau["Note fondamentale"].notna().sum()))

    recherche = st.text_input("🔍 Rechercher (ticker ou nom)", placeholder="ex. NVDA ou LVMH")
    affiche = tableau
    if recherche.strip():
        texte = recherche.strip().lower()
        affiche = tableau[tableau["Ticker"].str.lower().str.contains(texte, regex=False)
                          | tableau["Nom"].str.lower().str.contains(texte, regex=False)]

    note = lambda titre: st.column_config.NumberColumn(titre, format="%.1f /10")  # chiffre compact (iPhone)
    prix = st.column_config.NumberColumn(format="%.2f")
    colonnes = ["Ticker", "Nom", "Verdict", "Note technique", "Note fondamentale", "Cours",
                "Écart 200 WMA %", "Repli Fibo %", "RSI", "Croissance CA %/an", "PER", "Dette/EBITDA",
                "Seuil 1", "Seuil 2", "Seuil 3", "Stop"]
    st.dataframe(
        affiche[colonnes], hide_index=True, width="stretch", height=420,
        column_config={
            "Ticker": st.column_config.TextColumn(pinned=True),  # reste visible pendant le défilement
            "Nom": st.column_config.TextColumn(width="medium"),
            "Verdict": st.column_config.TextColumn(width="medium"),
            "Note technique": note("Note tech."),
            "Note fondamentale": note("Note fond."),
            "Cours": prix, "Seuil 1": prix, "Seuil 2": prix, "Seuil 3": prix, "Stop": prix,
            "Écart 200 WMA %": st.column_config.NumberColumn(format="%+.1f %%"),
            "Repli Fibo %": st.column_config.NumberColumn(format="%.0f %%"),
            "RSI": st.column_config.NumberColumn(format="%.0f"),
            "Croissance CA %/an": st.column_config.NumberColumn(format="%+.1f %%"),
            "PER": st.column_config.NumberColumn(format="%.1f"),
            "Dette/EBITDA": st.column_config.NumberColumn(format="%.1f"),
        },
    )
    st.caption(
        "🎯 Opportunité : les deux notes ≥ 7 · 👀 Surveiller : bonne note fondamentale (≥ 7), "
        "mais timing pas encore idéal · 🟡 Moyenne · ⛔ Fragile : note fondamentale < 4. "
        "Repli Fibo : 0 % = au sommet de la dernière hausse, 100 % = revenu au creux ; "
        "la zone d'achat va de 38,2 à 61,8 %. Faites glisser le tableau pour voir toutes les colonnes. "
        f"Dernière semaine de cours : {cours.index[-1]:%d/%m/%Y}."
    )

    # --- Fiche action ---
    st.divider()
    if affiche.empty:
        st.info("Aucune action ne correspond à la recherche.")
        return
    choix = st.selectbox("Voir la fiche de l'action", affiche["Ticker"],
                         format_func=lambda t: f"{t} — {noms.get(t, t)}")
    fiche_action(choix, noms.get(choix, choix), cours[choix].dropna(), choix in financieres)


# =============================================================================
# 11. PAGE « ALERTE ACHAT »
# =============================================================================
# Regroupe, sur les indices choisis, les actions dont :
#   - le RSI hebdomadaire est inférieur à 40 (l'action a beaucoup baissé récemment)
#   - ET la note fondamentale est supérieure ou égale à 7 (l'entreprise est solide)

RSI_ALERTE = 40
NOTE_FOND_ALERTE = 7


def page_alerte_achat():
    st.title("🚨 Alerte achat")
    st.caption(f"Actions avec un **RSI hebdomadaire < {RSI_ALERTE}** et une "
               f"**note fondamentale ≥ {NOTE_FOND_ALERTE}/10**.")

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
            for _, ligne in tableau[tableau["RSI"] < RSI_ALERTE].iterrows():
                if ligne["Ticker"] in series:  # action présente dans 2 indices (ex. Nasdaq 100 et S&P 500)
                    continue
                series[ligne["Ticker"]] = cours[ligne["Ticker"]].dropna()
                noms_tous[ligne["Ticker"]] = ligne["Nom"]
                candidats.append({**ligne.to_dict(), "Indice": nom_indice})

    if not candidats:
        st.success(f"Aucune action n'a un RSI hebdomadaire inférieur à {RSI_ALERTE} en ce moment.")
        return

    # --- 2. Note fondamentale de ces actions seulement (plus lent) ---
    st.caption(f"{len(candidats)} action(s) avec un RSI < {RSI_ALERTE} : calcul de leur note fondamentale…")
    comptes, erreurs = comptes_annuels([c["Ticker"] for c in candidats])
    alertes = []
    for c in candidats:
        t = c["Ticker"]
        if t not in comptes:
            continue
        f = analyse_fondamentale(comptes[t], series[t], t in financieres_toutes)
        if f["note"] is not None and f["note"] >= NOTE_FOND_ALERTE:
            alertes.append({**c, "Note fondamentale": f["note"],
                            "Croissance CA %/an": f["chiffres"].get("croissance_ca"),
                            "PER": f["chiffres"].get("per")})

    if erreurs:
        st.warning(f"Comptes indisponibles pour {len(erreurs)} action(s) : la liste est peut-être incomplète. "
                   "Yahoo limite sans doute les requêtes : patientez quelques minutes puis appuyez sur « Réessayer ».")
        if st.button("🔄 Réessayer", key="alerte_reessayer"):
            st.rerun()

    c1, c2 = st.columns(2)
    c1.metric(f"RSI < {RSI_ALERTE}", len(candidats))
    c2.metric("🚨 Alertes achat", len(alertes))

    if not alertes:
        st.info(f"Aucune action ne remplit les deux conditions pour le moment "
                f"(note fondamentale ≥ {NOTE_FOND_ALERTE} et RSI < {RSI_ALERTE}).")
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
# 12. NAVIGATION ENTRE LES PAGES
# =============================================================================
# Des boutons en haut de page plutôt qu'un menu latéral : plus pratique sur iPhone.
page = st.radio("Page", ["🎯 Opportunités", "🚨 Alerte achat"], horizontal=True,
                label_visibility="collapsed", key="page")
if page == "🎯 Opportunités":
    main()
else:
    page_alerte_achat()
st.caption("⚠️ Outil d'aide à la réflexion, pas un conseil en investissement. Données : Yahoo Finance.")
