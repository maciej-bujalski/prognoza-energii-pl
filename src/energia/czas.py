"""Czas polski na wykresach i w tabelach prognozy.

czas_lokalny z dim_czas to zegar bez strefy: w dobie zmiany czasu na zimowy godzina 2:00 wystepuje
dwa razy, a na letni 2:00 nie ma wcale. Dlatego kluczem jest zawsze godzina UTC, a do wyswietlania
uzywamy czasu ze strefa Europe/Warsaw (rozroznia obie godziny 2:00).
"""

import pandas as pd

PL = "Europe/Warsaw"
CELE = ["zapotrzebowanie", "wiatr", "pv"]


def czas_polski(godzina_utc: pd.Series) -> pd.Series:
    """Godzina UTC -> czas polski ze strefa (+01:00 albo +02:00)."""
    return pd.to_datetime(godzina_utc, utc=True).dt.tz_convert(PL)


def szeroka_prognoza(na_dobe: pd.DataFrame) -> pd.DataFrame:
    """Mediana prognozy (p50) w kolumnach wg celu, wiersz = godzina UTC; plus kolumna czas_polski."""
    szerokie = na_dobe.pivot(index="godzina_utc", columns="cel", values="p50")[CELE].sort_index()
    szerokie.columns.name = None
    szerokie["czas_polski"] = czas_polski(szerokie.index.to_series()).to_numpy()
    return szerokie
