"""Pobiera na komputer najnowsza baze i modele policzone przez codzienny workflow na GitHubie.

Uruchomienie: uv run python -m energia.synchronizuj
Wymaga zalogowanego GitHub CLI (gh auth login). Dane leza w wydaniu "dane" repozytorium.
"""

import shutil
import subprocess
import sys

from energia.pipeline import PROJEKT

REPO = "maciej-bujalski/prognoza-energii-pl"
POBIERZ = [
    ("data", ["energia.duckdb"]),
    ("data/model", ["*.txt", "*.json", "*.parquet"]),
]


def synchronizuj() -> None:
    if shutil.which("gh") is None:
        sys.exit("Brak GitHub CLI: zainstaluj (brew install gh) i zaloguj sie (gh auth login).")
    for katalog, wzorce in POBIERZ:
        cel = PROJEKT / katalog
        cel.mkdir(parents=True, exist_ok=True)
        polecenie = ["gh", "release", "download", "dane", "-R", REPO, "--dir", str(cel), "--clobber"]
        for wzorzec in wzorce:
            polecenie += ["--pattern", wzorzec]
        subprocess.run(polecenie, check=True)
    print("Pobrano najnowsze dane i modele z GitHuba.")


if __name__ == "__main__":
    synchronizuj()
