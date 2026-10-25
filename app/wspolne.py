"""Elementy wspolne dla stron aplikacji: motyw, naglowek, formatowanie, odczyt bazy."""

import duckdb
import pandas as pd
import streamlit as st

from energia.pipeline import BAZA
from energia.zdalne import czy_odswiezyc, pobierz_z_wydania

REPO = "https://github.com/maciej-bujalski/prognoza-energii-pl"
REZ = "Rezydualne"
PL = "Europe/Warsaw"
POLECENIE = "<code>uv run python -m energia.pipeline</code>"

# Dwa motywy. Kolory serii sa dobrane osobno pod kazde tlo i sprawdzone walidatorem
# palety (rozroznialnosc dla daltonistow, kontrast z tlem), nie odwrocone automatycznie.
MOTYWY = {
    "ciemny": {
        "tlo": "#0f1a24", "panel": "#162433", "linia": "#24384b",
        "tekst": "#e6edf2", "przygaszony": "#8ca0b3",
        "serie": {"Zapotrzebowanie": "#e6edf2", REZ: "#3987e5", "Wiatr": "#199e70", "Fotowoltaika": "#c98500"},
        # lata od najstarszego: najnowszy najjasniejszy, bo na ciemnym tle jasne = wyrazne
        "lata": ("#3f5f80", "#9ec5f4"),
        "skala": ["#162433", "#9ec5f4"],  # mapa ciepla: od tla do jasnego niebieskiego
    },
    "jasny": {
        "tlo": "#f2f5f7", "panel": "#ffffff", "linia": "#d5dee5",
        "tekst": "#14212b", "przygaszony": "#5b6b78",
        "serie": {"Zapotrzebowanie": "#14212b", REZ: "#2a78d6", "Wiatr": "#1baf7a", "Fotowoltaika": "#eda100"},
        "lata": ("#9ec5f4", "#1c5cab"),
        "skala": ["#f2f5f7", "#1c5cab"],
    },
}


def liczba(x: float) -> str:
    return f"{x:,.0f}".replace(",", "\u202f")


def procent(x: float) -> str:
    return f"{x:.0%}"


def ulamek(x: float, miejsca: int = 1) -> str:
    """Liczba z przecinkiem dziesietnym i prawdziwym minusem, np. -8.5 -> "−8,5"."""
    return f"{x:.{miejsca}f}".replace(".", ",").replace("-", "\u2212")


def rampa(od: str, do: str, n: int) -> list[str]:
    """n kolorow rowno rozlozonych miedzy dwoma (np. kolejne lata w odcieniach niebieskiego)."""
    a = [int(od[i : i + 2], 16) for i in (1, 3, 5)]
    b = [int(do[i : i + 2], 16) for i in (1, 3, 5)]
    kroki = [k / (n - 1) if n > 1 else 1.0 for k in range(n)]
    return ["#" + "".join(f"{round(x + (y - x) * t):02x}" for x, y in zip(a, b)) for t in kroki]


def motyw() -> dict:
    return MOTYWY["ciemny" if st.session_state.get("ciemny", True) else "jasny"]


def naglowek(strony: list) -> dict:
    """Pasek u gory: nazwa, linki do stron, przelacznik motywu. Wstrzykuje CSS motywu."""
    # Wybor trzymany w adresie strony, zeby przetrwal odswiezenie (?motyw=jasny)
    if "ciemny" not in st.session_state:
        st.session_state.ciemny = st.query_params.get("motyw", "ciemny") != "jasny"

    kolumny = st.columns([2.2] + [1] * len(strony) + [2, 1.6], vertical_alignment="center")
    kolumny[0].markdown('<p class="marka">Bilans KSE</p>', unsafe_allow_html=True)
    for kolumna, strona in zip(kolumny[1:], strony):
        kolumna.page_link(strona)
    ciemny = kolumny[-1].toggle("Tryb ciemny", key="ciemny")
    st.query_params["motyw"] = "ciemny" if ciemny else "jasny"

    m = motyw()
    SERIE = m["serie"]
    st.markdown(
        f"""
    <style>
      :root {{
        --tlo: {m["tlo"]}; --panel: {m["panel"]}; --linia: {m["linia"]};
        --tekst: {m["tekst"]}; --przygaszony: {m["przygaszony"]};
      }}
      .stApp {{ background: var(--tlo); color: var(--tekst); }}
      [data-testid="stHeader"] {{ display: none !important; }}
      .block-container {{ padding-top: 2rem; max-width: 1120px; }}
      .stApp p, .stApp li, .stApp label, .stApp summary, .stApp td {{ color: var(--tekst); }}
      .stApp a {{ color: {SERIE[REZ]}; }}

      .marka {{ font-family: "Barlow Semi Condensed"; font-weight: 600; font-size: 1.05rem;
                margin: 0; letter-spacing: .01em; }}
      .teza {{ font-family: "Barlow Semi Condensed"; font-weight: 500; color: var(--tekst);
               font-size: clamp(1.9rem, 4.2vw, 3.1rem); line-height: 1.08; letter-spacing: -.01em;
               margin: 1.6rem 0 1.4rem; max-width: 28ch; text-wrap: balance; font-variant-numeric: tabular-nums; }}

      .bilans {{ display: flex; gap: 2px; height: 46px; border-radius: 4px; overflow: hidden; }}
      .bilans div {{ height: 100%; }}
      .bilans-opis {{ display: flex; gap: 2px; margin-top: .45rem; }}
      .bilans-opis div {{ min-width: 5.5rem; font-size: .88rem; color: var(--przygaszony); line-height: 1.3;
                          overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
      .bilans-opis b {{ display: block; color: var(--tekst); font-weight: 600;
                        font-variant-numeric: tabular-nums; }}
      .porownanie {{ color: var(--przygaszony) !important; font-size: .92rem; margin: 1.1rem 0 2.2rem; }}

      h2, h3 {{ font-family: "Barlow Semi Condensed" !important; font-weight: 600 !important;
                color: var(--tekst) !important; }}
      .przypis {{ color: var(--przygaszony) !important; font-size: .85rem; }}
      .notatka {{ border-left: 2px solid var(--linia); padding: .1rem 0 .1rem .9rem; margin: 0 0 1.05rem; max-width: 62ch; }}
      .notatka b {{ font-weight: 600; }}
      code {{ background: var(--panel) !important; color: var(--tekst) !important; }}

      table.lista {{ border-collapse: collapse; width: 100%; font-size: .92rem; }}
      table.lista td, table.lista th {{ border: none; border-bottom: 1px solid var(--linia);
                                       padding: .42rem .35rem; text-align: left; }}
      table.lista th {{ color: var(--przygaszony); font-weight: 500; }}
      table.lista .nr {{ color: var(--przygaszony); width: 1.6rem; }}
      table.lista .prawo {{ text-align: right; font-variant-numeric: tabular-nums; white-space: nowrap; }}
      table.lista td.czeka {{ color: var(--przygaszony); }}
      .przewijana {{ max-height: 360px; overflow-y: auto; }}

      /* Kontrolki Streamlit dopasowane do motywu */
      [data-testid="stButtonGroup"] button {{ background: var(--panel); color: var(--tekst);
                                              border-color: var(--linia); }}
      [data-testid="stButtonGroup"] button[kind$="Active"] {{ border-color: {SERIE[REZ]}; color: {SERIE[REZ]}; }}
      [data-testid="stExpander"] details {{ border-color: var(--linia); background: var(--panel); }}
      [data-testid="stExpander"] summary:hover {{ color: {SERIE[REZ]}; }}
      [data-testid="stWidgetLabel"] p {{ color: var(--tekst); }}
      #vg-tooltip-element {{ background: var(--panel); color: var(--tekst); border: 1px solid var(--linia);
                             font-family: Barlow, sans-serif; box-shadow: none; }}
      #vg-tooltip-element td.key {{ color: var(--przygaszony); }}
      hr {{ border-color: var(--linia) !important; }}
      .legenda {{ display: flex; flex-wrap: wrap; gap: .35rem 1.3rem; font-size: .9rem; margin: .2rem 0 -.4rem; }}
      .legenda span {{ display: inline-flex; align-items: center; gap: .45rem; }}
      .legenda i.kreska {{ width: 16px; height: 2px; border-radius: 1px; }}
      .legenda i.pole {{ width: 11px; height: 11px; border-radius: 2px; opacity: .8; }}
      [data-testid="stPageLink"] a {{ padding: .2rem .5rem; border-radius: 4px; }}
      [data-testid="stPageLink"] a span {{ color: var(--przygaszony) !important; font-weight: 500; }}
      [data-testid="stPageLink"] a[aria-current="page"] span {{ color: var(--tekst) !important; }}
      [data-testid="stPageLink"] a[aria-current="page"] {{ box-shadow: inset 0 -2px 0 {SERIE[REZ]}; border-radius: 0; }}
      [data-testid="stPageLink"] a:hover {{ background: var(--panel); }}
      [data-testid="stCheckbox"] label:has(input:not(:checked)) > span + div {{ background: var(--linia); }}
      [data-testid="stCheckbox"] label > span + div > div {{ background: var(--panel);
                                                            box-shadow: 0 0 0 1px var(--linia); }}
    </style>
    """,
        unsafe_allow_html=True,
    )
    return m


def komunikat(tytul: str, tresc: str) -> None:
    st.markdown(f'<h1 class="teza">{tytul}</h1><p>{tresc}</p>', unsafe_allow_html=True)
    st.stop()


@st.cache_resource(show_spinner=False)
def _pobierz_raz(wersja_bazy: float) -> None:
    """Pobranie z GitHuba najwyzej raz na dana wersje bazy. cache_resource blokuje wywolania
    z innych sesji, dopoki pierwsze trwa: kilku odwiedzajacych naraz nie sciaga pliku rownolegle."""
    pobierz_z_wydania(BAZA.parents[1])
    st.cache_data.clear()  # stare wyniki zapytan nie pasuja do nowej bazy


def sprawdz_baze() -> None:
    """Pilnuje swiezosci danych: gdy bazy nie ma albo ma ponad 6 h, pobiera najnowsza z GitHuba
    (wydanie "dane", ktore codziennie aktualizuje workflow). Tak dziala tez wersja w chmurze."""
    if czy_odswiezyc(BAZA, max_wiek_h=6):
        try:
            with st.spinner("Pobieram najnowsze dane…"):
                _pobierz_raz(BAZA.stat().st_mtime if BAZA.exists() else 0.0)
        except Exception:
            if not BAZA.exists():
                komunikat("Nie udało się pobrać danych.", f"Sprawdź połączenie albo uruchom {POLECENIE}.")
            # jest starsza baza: pokazujemy ja zamiast bledu


@st.cache_data(ttl=600, show_spinner=False)
def zapytanie(sql: str) -> pd.DataFrame:
    """Zapytanie do bazy tylko do odczytu (nie blokuje pipeline'u)."""
    with duckdb.connect(str(BAZA), read_only=True) as con:
        con.execute("set TimeZone = 'UTC'")
        return con.sql(sql).df()


def os_y_mw(**kwargs) -> "alt.Axis":
    import altair as alt

    # d3-format w Vega nie zna polskiego locale, wiec separator tysiecy podmieniam recznie
    return alt.Axis(domain=False, tickCount=5, labelExpr="replace(format(datum.value, ',.0f'), /,/g, '\u00a0')", **kwargs)


def wyglad(wykres, m: dict, wysokosc: int = 380):
    """Kolory osi i fonty wykresu Altair dopasowane do motywu."""
    return (
        wykres.properties(height=wysokosc, background="transparent")
        .configure_view(strokeWidth=0)
        .configure_axis(
            labelColor=m["przygaszony"], titleColor=m["przygaszony"], gridColor=m["linia"],
            tickColor=m["linia"], domainColor=m["linia"], labelFont="Barlow", titleFont="Barlow", labelFontSize=12,
        )
        .configure_legend(labelColor=m["tekst"], titleColor=m["przygaszony"], labelFont="Barlow", titleFont="Barlow")
    )
