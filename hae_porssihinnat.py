#!/usr/bin/env python3
"""
Hakee Suomen pörssisähkön tuntihinnat sahkotin.fi-rajapinnasta ja
tallentaa ne CSV-tiedostoon.

LÄHDE:
sahkotin.fi (ylläpitäjä Pakastin Oy, hintadatan omistaa Nord Pool).
Ilmainen, avoin API ei-kaupalliseen käyttöön. Ei vaadi rekisteröitymistä
tai API-avainta.

HUOM tuntihintojen taustasta: Suomi siirtyi 15 minuutin (vartti-)
markkina-aikaan 1.10.2025 alkaen. Kun tältä API:lta pyydetään
TUNTIHINTOJA (ilman &quarter-parametria, kuten tässä skriptissä),
palvelu laskee tunnin hinnaksi kyseisen tunnin neljän vartin
keskiarvon - tämä sopii suoraan yhteen oman kulutusdatamme
tuntitarkkuuden kanssa.

Käyttö:
    python3 hae_porssihinnat.py ALKU_ISO LOPPU_ISO [output.csv]

Esimerkki:
    python3 hae_porssihinnat.py 2026-08-28T00:00:00Z 2026-08-30T00:00:00Z porssihinnat.csv

Käyttö moduulina:
    from hae_porssihinnat import fetch_prices
    prices = fetch_prices(start_iso, end_iso)  # -> dict {utc_hour_datetime: hinta_snt_kwh}
"""

import sys
import csv
import json
import urllib.request
import urllib.parse
from datetime import datetime, timezone

API_BASE = "https://sahkotin.fi/prices"


def fetch_prices(start_iso: str, end_iso: str, quarter: bool = False) -> dict:
    """Hakee hinnat (snt/kWh, ILMAN ALV:tä) väliltä [start_iso, end_iso).
    quarter=True hakee varttihinnat (15 min), quarter=False tuntihinnat (60 min,
    palvelimen laskema tasapainoinen keskiarvo neljästä vartista).

    Palauttaa dictin {utc_datetime: hinta_snt_kwh}.

    HUOM: haetaan tarkoituksella ilman ALV:tä (ei &vat-parametria), koska
    sähkösopimuksen marginaali lisätään aina ennen ALV:n laskentaa - ALV
    lasketaan vasta (spot-hinta + marginaali) -summalle. Marginaalin ja
    ALV:n lisääminen tehdään update_summary.py:ssä (compute_costs)."""
    params = {
        "fix": "",   # €/MWh -> snt/kWh
        "start": start_iso,
        "end": end_iso,
    }
    if quarter:
        params["quarter"] = ""
    query = urllib.parse.urlencode(params)
    url = f"{API_BASE}?{query}"

    req = urllib.request.Request(url, headers={"User-Agent": "goe-logger-hintahaku/1.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        if resp.status != 200:
            raise RuntimeError(f"Odottamaton HTTP-status hintahaussa: {resp.status}")
        data = json.loads(resp.read().decode("utf-8"))

    prices = {}
    for entry in data.get("prices", []):
        ts = datetime.fromisoformat(entry["date"].replace("Z", "+00:00"))
        prices[ts] = float(entry["value"])
    return prices


def main():
    if len(sys.argv) < 3:
        print("Käyttö: python3 hae_porssihinnat.py ALKU_ISO LOPPU_ISO [output.csv]")
        sys.exit(1)

    start_iso, end_iso = sys.argv[1], sys.argv[2]
    output_path = sys.argv[3] if len(sys.argv) > 3 else "porssihinnat.csv"

    prices = fetch_prices(start_iso, end_iso)

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["tunti_utc", "hinta_snt_kwh"])
        for ts in sorted(prices):
            writer.writerow([ts.isoformat(), prices[ts]])

    print(f"Tallennettu {len(prices)} tuntihintaa tiedostoon {output_path}")


if __name__ == "__main__":
    main()
