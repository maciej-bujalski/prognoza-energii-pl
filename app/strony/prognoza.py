"""Strona Prognoza: prognoza modelu na jutro, jakosc w backteście, trafnosc na zywo, waznosc cech."""

import json
from datetime import date, timedelta

import altair as alt
import duckdb
import pandas as pd
import streamlit as st

from energia.czas import czas_polski, szeroka_prognoza
from energia.model.monitoring import ocen_ostatnie_dni
from energia.model.trening import KATALOG
from wspolne import PL, REZ, komunikat, liczba, motyw, os_y_mw, procent, sprawdz_baze, ulamek, wyglad, zapytanie

m = motyw()
SERIE = m["serie"]
NAZWY = {"zapotrzebowanie": "Zapotrzebowanie", "wiatr": "Wiatr", "pv": "Fotowoltaika"}
KOLORY = {"zapotrzebowanie": SERIE[REZ], "wiatr": SERIE["Wiatr"], "pv": SERIE["Fotowoltaika"]}
CECHY = {
    "godzina": "godzina", "dzien_tygodnia": "dzień tygodnia", "miesiac": "miesiąc", "dzien_roku": "dzień roku",
    "czy_swieto": "święto", "czy_dzien_roboczy": "dzień roboczy", "wysokosc_slonca": "wysokość słońca",
    "temperatura_c": "temperatura", "wiatr_100m_sredni_kmh": "wiatr 100 m (śr.)",
    "promieniowanie_srednie_wm2": "promieniowanie (śr.)", "zachmurzenie_srednie_proc": "zachmurzenie",
    "wiatr_pomorze_kmh": "wiatr: Pomorze", "wiatr_wielkopolska_kmh": "wiatr: Wielkopolska",
    "wiatr_lubelskie_kmh": "wiatr: Lubelskie", "promieniowanie_lubelskie_wm2": "promień.: Lubelskie",
    "promieniowanie_slask_wm2": "promień.: Śląsk", "promieniowanie_wielkopolska_wm2": "promień.: Wielkopolska",
}


def nazwa_cechy(c: str) -> str:
    # kazdy wykres dotyczy jednego celu, wiec przy opoznieniach wystarczy "kiedy", bez nazwy celu
    for przyrostek, opis in (("_lag48", "2 dni temu"), ("_lag168", "tydzień temu"),
                             ("_srednia_d2", "średnia sprzed 2 dni"), ("_max30", "maks. z 30 dni")):
        if c.endswith(przyrostek):
            return opis
    return CECHY.get(c, c)


sprawdz_baze()
if not (KATALOG / "metryki.json").exists():
    komunikat("Model nie jest jeszcze wytrenowany.", "Uruchom <code>uv run python -m energia.model.trening</code>.")

try:
    prognozy = zapytanie("""
        with najnowsze as (
            select * from prognozy_modelu
            qualify wygenerowano_utc = max(wygenerowano_utc) over ()
        )
        select n.*, c.czas_lokalny, c.data
        from najnowsze n join marts.dim_czas c using (godzina_utc)
        order by godzina_utc
    """)
    plan = zapytanie("""
        select c.godzina_utc, c.data,
               avg(p.zapotrzebowanie_plan_mw) as zapotrzebowanie, avg(p.wiatr_plan_mw) as wiatr, avg(p.pv_plan_mw) as pv
        from staging.stg_plan_pse p
        join marts.dim_czas c on c.godzina_utc = date_trunc('hour', p.kwadrans_od_utc)
        where p.znany_przed_doba
          and p.publikacja_utc = (select max(publikacja_utc) from staging.stg_plan_pse x
                                  where x.doba = p.doba and x.znany_przed_doba)
        group by 1, 2
    """)
    ocena = zapytanie("select * from marts.fct_ocena_prognoz where faktyczne is not null")
except duckdb.IOException:
    komunikat("Trwa aktualizacja danych.", "Pipeline zapisuje teraz bazę. Odśwież stronę za kilka minut.")
except duckdb.CatalogException:
    komunikat("Brak tabel prognoz.", "Uruchom <code>uv run python -m energia.pipeline</code>.")

if prognozy.empty:
    komunikat("Nie ma jeszcze prognozy.", "Uruchom <code>uv run python -m energia.model.prognoza</code>.")

metryki = json.loads((KATALOG / "metryki.json").read_text())
backtest = pd.read_parquet(KATALOG / "backtest.parquet")
waznosc = json.loads((KATALOG / "waznosc_cech.json").read_text()) if (KATALOG / "waznosc_cech.json").exists() else {}

# --- Teza: co bedzie jutro -------------------------------------------------------------
# DuckDB oddaje daty jako datetime64; zamieniamy na date, zeby porownania z date.today() dzialaly
for ramka in (prognozy, plan):
    ramka["data"] = pd.to_datetime(ramka["data"]).dt.date
doba = prognozy["data"].max()
na_dobe = prognozy[prognozy["data"] == doba].assign(czas_polski=lambda d: czas_polski(d["godzina_utc"]))
# kluczem jest godzina UTC: w dobie zmiany czasu zegar lokalny ma dwie godziny 2:00 (albo zadnej)
szerokie = szeroka_prognoza(na_dobe)
szczyt = szerokie.loc[szerokie["zapotrzebowanie"].idxmax(), "czas_polski"]
oze_udzial = (szerokie["wiatr"] + szerokie["pv"]).sum() / szerokie["zapotrzebowanie"].sum()
kiedy = "Jutro" if doba == date.today() + timedelta(days=1) else f"{doba:%d.%m}"
wygenerowano = pd.Timestamp(prognozy["wygenerowano_utc"].iloc[0]).tz_convert(PL)
st.markdown(
    f'<h1 class="teza">{kiedy} model spodziewa się szczytu {liczba(szerokie["zapotrzebowanie"].max())} MW '
    f"o {szczyt:%H}:00. Wiatr i słońce pokryją ok. {procent(oze_udzial)} zapotrzebowania.</h1>",
    unsafe_allow_html=True,
)
st.markdown(
    f'<p class="porownanie">Prognoza na {doba:%d.%m.%Y} policzona {wygenerowano:%d.%m o %H:%M}. '
    "Pas wokół linii to przedział 80%: w 8 na 10 godzin wynik powinien się w nim zmieścić. "
    "Linia przerywana to plan PSE opublikowany przed dobą (gdy już jest).</p>",
    unsafe_allow_html=True,
)

# --- Wykresy prognozy: trzy male wykresy, kazdy w swojej skali -------------------------------
plan_doby = plan[plan["data"] == doba]
for cel in ("zapotrzebowanie", "wiatr", "pv"):
    dane = na_dobe[na_dobe["cel"] == cel].assign(
        **{"MW": lambda d: d["p50"], "od": lambda d: d["p10"], "do": lambda d: d["p90"]}
    )
    baza = alt.Chart(dane).encode(
        x=alt.X("czas_polski:T", title=None, axis=alt.Axis(format="%H:%M", labelAngle=0, grid=False, tickCount=12))
    )
    # zapotrzebowanie nie zaczyna sie od zera, zeby bylo widac zmiennosc w ciagu doby
    skala_y = alt.Scale(zero=cel != "zapotrzebowanie")
    pas = baza.mark_area(opacity=0.25, color=KOLORY[cel]).encode(
        y=alt.Y("od:Q", title="MW", axis=os_y_mw(), scale=skala_y), y2="do:Q"
    )
    linia = baza.mark_line(strokeWidth=2.4, color=KOLORY[cel]).encode(
        y="MW:Q",
        tooltip=[alt.Tooltip("czas_polski:T", title="Godzina", format="%H:%M"),
                 alt.Tooltip("p50:Q", title="Prognoza (MW)", format=",.0f"),
                 alt.Tooltip("p10:Q", title="Dolna granica", format=",.0f"),
                 alt.Tooltip("p90:Q", title="Górna granica", format=",.0f")],
    )
    warstwy = [pas, linia]
    if not plan_doby.empty:
        p = plan_doby.merge(dane[["godzina_utc", "czas_polski"]], on="godzina_utc")
        warstwy.append(alt.Chart(p).mark_line(strokeWidth=1.6, strokeDash=[5, 4], color=m["przygaszony"]).encode(
            x="czas_polski:T", y=f"{cel}:Q",
            tooltip=[alt.Tooltip("czas_polski:T", title="Godzina", format="%H:%M"),
                     alt.Tooltip(f"{cel}:Q", title="Plan PSE (MW)", format=",.0f")]))
    st.markdown(f"<h3>{NAZWY[cel]}</h3>", unsafe_allow_html=True)
    st.altair_chart(wyglad(alt.layer(*warstwy), m, 220), width="stretch", theme=None)

st.divider()

# --- Jakosc w backteście -------------------------------------------------------------------
st.subheader("Jak dobry jest model")
mies = metryki["zapotrzebowanie_mw"]
st.markdown(
    f"<p>Backtest z rosnącym oknem: każdy miesiąc prognozowany modelem uczonym tylko na danych sprzed tego "
    f"miesiąca, z cechami znanymi dzień wcześniej. Okres: {pd.Timestamp(mies['od']):%m.%Y} – "
    f"{pd.Timestamp(mies['do']):%m.%Y}. Błąd to średni błąd bezwzględny jako procent średniej wartości (nMAE).</p>",
    unsafe_allow_html=True,
)
wiersze = ""
for kolumna, klucz in (("zapotrzebowanie_mw", "zapotrzebowanie"), ("wiatr_mw", "wiatr"), ("pv_mw", "pv")):
    w = metryki[kolumna]
    wiersze += (
        f"<tr><td>{NAZWY[klucz]}</td><td class='prawo'><b>{ulamek(w['model']['nmae'] * 100)}%</b></td>"
        f"<td class='prawo'>{ulamek(w['naiwna']['nmae'] * 100)}%</td>"
        f"<td class='prawo'>{ulamek(w['plan_pse_ostatni']['nmae'] * 100)}%</td>"
        f"<td class='prawo'>{liczba(w['model']['mae'])} MW</td>"
        f"<td class='prawo'>{procent(w['pokrycie_80'])} → {procent(w.get('kalibracja', {}).get('pokrycie_po_poza_proba', w['pokrycie_80']))}</td></tr>"
    )
st.markdown(
    "<table class='lista'><tr><th>Cel</th><th class='prawo'>Model</th><th class='prawo'>Prognoza naiwna</th>"
    "<th class='prawo'>Plan PSE (wersja ostatnia)*</th><th class='prawo'>Błąd modelu</th>"
    f"<th class='prawo'>W przedziale 80%: przed → po kalibracji</th></tr>{wiersze}</table>"
    '<p class="przypis">Prognoza naiwna: zapotrzebowanie jak tydzień temu, wiatr i PV jak dwa dni temu o tej godzinie. '
    "* Wersja ostatnia planu PSE jest poprawiana w trakcie doby, więc zna część przyszłości i nie jest "
    "uczciwym benchmarkiem. Uczciwe porównanie (plan sprzed doby) rośnie w sekcji poniżej. "
    "Surowe przedziały kwantylowe były za wąskie, więc są poszerzane kalibracją konformalną; "
    "wynik „po” zmierzony na 6 miesiącach, których kalibracja nie widziała. "
    "Model uczy się na archiwalnych prognozach pogody o krótkim horyzoncie, więc w produkcji, z prognozą "
    "pogody na następny dzień, błąd będzie nieco większy.</p>",
    unsafe_allow_html=True,
)
miesiecznie = (
    backtest.assign(blad=lambda d: (d["p50"] - d["faktyczne"]).abs())
    .groupby(["cel", "miesiac"])
    .apply(lambda g: g["blad"].mean() / g["faktyczne"].mean(), include_groups=False)
    .rename("nmae").reset_index()
)
miesiecznie["cel"] = miesiecznie["cel"].map({"zapotrzebowanie_mw": "Zapotrzebowanie", "wiatr_mw": "Wiatr", "pv_mw": "Fotowoltaika"})
miesiecznie["miesiac"] = pd.to_datetime(miesiecznie["miesiac"])
wykres = (
    alt.Chart(miesiecznie)
    .mark_line(point=alt.OverlayMarkDef(size=40), strokeWidth=2)
    .encode(
        x=alt.X("miesiac:T", title=None, axis=alt.Axis(format="%m.%Y", labelAngle=0, grid=False)),
        y=alt.Y("nmae:Q", title="nMAE", axis=alt.Axis(format="%", domain=False, tickCount=5)),
        color=alt.Color("cel:N", scale=alt.Scale(domain=["Zapotrzebowanie", "Wiatr", "Fotowoltaika"],
                        range=[KOLORY["zapotrzebowanie"], KOLORY["wiatr"], KOLORY["pv"]]),
                        legend=alt.Legend(title=None, orient="top")),
        tooltip=[alt.Tooltip("cel:N", title="Cel"), alt.Tooltip("miesiac:T", title="Miesiąc", format="%m.%Y"),
                 alt.Tooltip("nmae:Q", title="nMAE", format=".1%")],
    )
)
st.altair_chart(wyglad(wykres, m, 260), width="stretch", theme=None)

st.divider()

# --- Trafnosc na zywo ------------------------------------------------------------------------
st.subheader("Trafność na żywo: model kontra plan PSE sprzed doby")
if ocena.empty:
    st.markdown(
        "<p>Pierwsze rozliczenie pojawi się, gdy minie doba z prognozą policzoną dzień wcześniej. "
        "Od tego momentu codziennie przybywa jedna doba porównania na równych zasadach: model i PSE "
        "znają tylko to, co było wiadomo przed północą.</p>",
        unsafe_allow_html=True,
    )
else:
    # ta sama funkcja co w codziennym monitoringu: model i PSE porownane na tych samych godzinach
    ocena["doba"] = pd.to_datetime(ocena["doba"]).dt.date
    wyniki = ocen_ostatnie_dni(ocena, dzis=date.today(), dni=3650)
    wiersze = ""
    for cel in ("zapotrzebowanie", "wiatr", "pv"):
        if cel not in wyniki:
            continue
        w = wyniki[cel]
        if w["nmae_pse"] is None:
            porownanie = "<td class='prawo czeka' colspan='2'>brak planu sprzed doby</td>"
        else:
            porownanie = (f"<td class='prawo'><b>{ulamek(w['nmae_model_wspolne'] * 100)}%</b></td>"
                          f"<td class='prawo'>{ulamek(w['nmae_pse'] * 100)}%</td>")
        wiersze += (
            f"<tr><td>{NAZWY[cel]}</td><td class='prawo'>{w['dob']}</td>"
            f"<td class='prawo'>{ulamek(w['nmae_model'] * 100)}%</td><td class='prawo'>{procent(w['pokrycie'])}</td>"
            f"<td class='prawo'>{w['dob_z_planem']}</td>{porownanie}</tr>"
        )
    st.markdown(
        "<table class='lista'><tr><th>Cel</th><th class='prawo'>Dób</th><th class='prawo'>Model (nMAE)</th>"
        "<th class='prawo'>W przedziale 80%</th><th class='prawo'>Dób z planem PSE</th>"
        "<th class='prawo'>Model</th><th class='prawo'>Plan PSE</th></tr>"
        f"{wiersze}</table>"
        '<p class="przypis">Ostatnie dwie kolumny: model i plan PSE porównane wyłącznie na godzinach, dla których '
        "archiwum ma plan opublikowany przed dobą. Plan na jutro PSE publikuje wieczorem, więc pipeline "
        "uruchamia się też wieczorem, żeby go zapisać, zanim zostanie poprawiony.</p>",
        unsafe_allow_html=True,
    )

st.divider()

# --- Waznosc cech ------------------------------------------------------------------------------
if waznosc:
    st.subheader("Co napędza prognozę")
    st.markdown(
        "<p>Średni wpływ cechy na prognozę (wartości SHAP z ostatnich 60 dni, model mediany). "
        "Dla wiatru i PV model prognozuje ułamek maksimum z 30 dni, więc wpływ jest w tej skali.</p>",
        unsafe_allow_html=True,
    )
    kolumny = st.columns(3, gap="large")
    for kolumna, cel in zip(kolumny, ("zapotrzebowanie", "wiatr", "pv")):
        top = pd.Series(waznosc[cel]).head(8).rename_axis("cecha").reset_index(name="wplyw")
        top["cecha"] = top["cecha"].map(nazwa_cechy)
        wykres = (
            alt.Chart(top)
            .mark_bar(color=KOLORY[cel], cornerRadiusEnd=3, height=14)
            .encode(
                x=alt.X("wplyw:Q", title=None, axis=alt.Axis(labels=False, ticks=False, domain=False, grid=False)),
                y=alt.Y("cecha:N", sort="-x", title=None, axis=alt.Axis(labelLimit=150, domain=False, ticks=False, labelPadding=6)),
                tooltip=[alt.Tooltip("cecha:N", title="Cecha"), alt.Tooltip("wplyw:Q", title="Średni |SHAP|", format=".3f")],
            )
        )
        with kolumna:
            st.markdown(f"<h3>{NAZWY[cel]}</h3>", unsafe_allow_html=True)
            st.altair_chart(wyglad(wykres, m, 230), width="stretch", theme=None)
