"""Pobieranie danych z wydania "dane" na GitHubie: z tego korzysta aplikacja w chmurze.

Codzienny workflow zapisuje tam baze i wyniki modelu. Aplikacja na Streamlit Community Cloud
nie ma wlasnego pipeline'u, wiec przy starcie (i potem co kilka godzin) sciaga gotowe pliki.
"""

import os
import time
from collections.abc import Callable
from pathlib import Path

import httpx

from energia.http import pobierz

URL = "https://github.com/maciej-bujalski/prognoza-energii-pl/releases/download/dane"
# (katalog wzgledem projektu, nazwa pliku): tylko to, czego potrzebuje aplikacja
PLIKI = [
    ("data", "energia.duckdb"),
    ("data", "dbt_wyniki_testow.json"),
    ("data/model", "metryki.json"),
    ("data/model", "backtest.parquet"),
    ("data/model", "waznosc_cech.json"),
]


def czy_odswiezyc(baza: Path, max_wiek_h: float) -> bool:
    """True, gdy bazy nie ma albo jest starsza niz max_wiek_h godzin."""
    return not baza.exists() or time.time() - baza.stat().st_mtime > max_wiek_h * 3600


def pobierz_z_wydania(
    katalog: Path,
    klient: httpx.Client | None = None,
    czekaj: Callable[[float], None] = time.sleep,
) -> None:
    """Sciaga pliki z PLIKI do katalogu projektu.

    Kazdy plik najpierw trafia do pliku tymczasowego, a dopiero po pelnym pobraniu zastepuje
    stary (os.replace jest atomowe). Przerwane pobieranie nie zostawia polowy bazy.
    """
    wlasny_klient = klient is None
    klient = klient or httpx.Client(timeout=120, follow_redirects=True)
    try:
        for podkatalog, nazwa in PLIKI:
            cel = katalog / podkatalog / nazwa
            cel.parent.mkdir(parents=True, exist_ok=True)
            tymczasowy = cel.with_suffix(cel.suffix + ".pobieranie")
            tymczasowy.write_bytes(pobierz(klient, f"{URL}/{nazwa}", czekaj=czekaj).content)
            os.replace(tymczasowy, cel)
    finally:
        if wlasny_klient:
            klient.close()
