"""Testy prognozy na dobe przy zmianie czasu (doba 23- i 25-godzinna)."""

import pandas as pd

from energia.czas import szeroka_prognoza


def prognoza_na_dobe(start_utc: str, godzin: int) -> pd.DataFrame:
    """Prognoza dla trzech celow; czas_lokalny jak w dim_czas: lokalny zegar bez strefy."""
    utc = pd.date_range(start_utc, periods=godzin, freq="h", tz="UTC")
    lokalny = utc.tz_convert("Europe/Warsaw").tz_localize(None)
    return pd.concat([
        pd.DataFrame({"godzina_utc": utc, "czas_lokalny": lokalny, "cel": cel, "p50": range(godzin)})
        for cel in ("zapotrzebowanie", "wiatr", "pv")
    ], ignore_index=True)


def test_doba_25_godzin_przy_zmianie_na_czas_zimowy():
    # 25.10.2026: zegar cofa sie z 3:00 na 2:00, godzina 2:00 wystepuje dwa razy
    na_dobe = prognoza_na_dobe("2026-10-24 22:00", 25)
    assert na_dobe["czas_lokalny"].duplicated().any()

    szerokie = szeroka_prognoza(na_dobe)

    assert len(szerokie) == 25
    assert szerokie.index.is_monotonic_increasing
    assert list(szerokie.columns[:3]) == ["zapotrzebowanie", "wiatr", "pv"]
    dwie_druga = szerokie[szerokie["czas_polski"].dt.hour == 2]
    assert len(dwie_druga) == 2
    assert [str(t.utcoffset()) for t in dwie_druga["czas_polski"]] == ["2:00:00", "1:00:00"]


def test_zwykla_doba():
    szerokie = szeroka_prognoza(prognoza_na_dobe("2026-11-10 23:00", 24))

    assert len(szerokie) == 24
    assert szerokie["czas_polski"].iloc[0].hour == 0
