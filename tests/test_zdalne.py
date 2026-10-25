"""Testy pobierania danych z wydania "dane" na GitHubie (dla aplikacji w chmurze)."""

import os
import time

import httpx

from energia.zdalne import PLIKI, URL, czy_odswiezyc, pobierz_z_wydania


def test_pobiera_wszystkie_pliki_idac_za_przekierowaniem(tmp_path):
    # GitHub odpowiada na link do zalacznika przekierowaniem (302) na serwer z plikami
    def obsluga(zadanie: httpx.Request) -> httpx.Response:
        if zadanie.url.host == "github.com":
            return httpx.Response(302, headers={"location": f"https://pliki.test/{zadanie.url.path.rsplit('/', 1)[-1]}"})
        return httpx.Response(200, content=f"zawartosc {zadanie.url.path}".encode())

    pobierz_z_wydania(tmp_path, klient=httpx.Client(transport=httpx.MockTransport(obsluga), follow_redirects=True))

    for katalog, nazwa in PLIKI:
        assert (tmp_path / katalog / nazwa).read_bytes() == f"zawartosc /{nazwa}".encode()


def test_adres_wskazuje_wydanie_dane_publicznego_repo():
    assert URL == "https://github.com/maciej-bujalski/prognoza-energii-pl/releases/download/dane"


def test_nieudane_pobranie_nie_niszczy_poprzedniego_pliku(tmp_path):
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "energia.duckdb").write_bytes(b"stara baza")

    def obsluga(zadanie: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    try:
        pobierz_z_wydania(tmp_path, klient=httpx.Client(transport=httpx.MockTransport(obsluga)), czekaj=lambda s: None)
    except Exception:
        pass

    assert (tmp_path / "data" / "energia.duckdb").read_bytes() == b"stara baza"


def test_odswiezanie_gdy_bazy_brak_albo_jest_starsza_niz_limit(tmp_path):
    baza = tmp_path / "energia.duckdb"
    assert czy_odswiezyc(baza, max_wiek_h=6)

    baza.write_bytes(b"x")
    assert not czy_odswiezyc(baza, max_wiek_h=6)

    stary = time.time() - 7 * 3600
    os.utime(baza, (stary, stary))
    assert czy_odswiezyc(baza, max_wiek_h=6)
