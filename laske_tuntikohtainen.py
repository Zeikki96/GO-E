#!/usr/bin/env python3
"""
Muuntaa goe_log.csv-lokin tuntikohtaiseksi energiankulutukseksi (kWh/tunti).

MENETELMÄ (tarkka, ei approksimoitu):
go-e:n "lifetime_energy_kwh" (API-kenttä eto) on laturin elinikäinen,
aina kasvava kokonaisenergialaskuri - se ei nollaudu koskaan, ei edes
kun yksittäinen lataussessio päättyy. Se toimii siis kuin sähkömittarin
lukema: kahden peräkkäisen mittauksen EROTUS kertoo täsmälleen, paljonko
energiaa kului niiden välissä - ei tarvitse arvata tehon pysyneen
vakiona, koska laturi on jo itse integroinut sen puolestamme.

Jos kahden otoksen välinen aika on epänormaalin pitkä (esim. skripti
ollut pois päältä), väli ohitetaan, ettei siihen kertyneestä energiasta
tule virheellisesti yhteen tuntiin lisättyä piikkiä.

Käyttö komentoriviltä:
    python3 laske_tuntikohtainen.py [polku/goe_log.csv]

Käyttö moduulina (esim. update_summary.py):
    from laske_tuntikohtainen import compute_hourly
    hourly = compute_hourly("goe_log.csv")  # -> list of (datetime, kwh), aikajärjestyksessä
"""

import sys
import csv
from datetime import datetime, timedelta
from collections import defaultdict

MAX_GAP_HOURS = 2  # jos otosten väli on tätä pidempi, ohitetaan (esim. skripti ollut pois päältä)


def compute_hourly(path: str):
    """Palauttaa listan (tunnin_alkuaika: datetime, kwh: float), aikajärjestyksessä."""
    rows = []
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            r["timestamp"] = datetime.fromisoformat(r["timestamp"])
            r["lifetime_energy_kwh"] = float(r["lifetime_energy_kwh"])
            rows.append(r)

    rows.sort(key=lambda r: r["timestamp"])

    hourly_kwh = defaultdict(float)

    for i in range(1, len(rows)):
        prev, cur = rows[i - 1], rows[i]

        dt = cur["timestamp"] - prev["timestamp"]
        if dt <= timedelta(0) or dt > timedelta(hours=MAX_GAP_HOURS):
            continue

        energy_diff = cur["lifetime_energy_kwh"] - prev["lifetime_energy_kwh"]
        if energy_diff <= 0:
            continue

        t0, t1 = prev["timestamp"], cur["timestamp"]
        total_seconds = (t1 - t0).total_seconds()

        cursor = t0
        while cursor < t1:
            hour_start = cursor.replace(minute=0, second=0, microsecond=0)
            next_hour = hour_start + timedelta(hours=1)
            segment_end = min(t1, next_hour)
            segment_seconds = (segment_end - cursor).total_seconds()
            share = segment_seconds / total_seconds
            hourly_kwh[hour_start] += energy_diff * share
            cursor = segment_end

    return sorted(hourly_kwh.items())


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else "goe_log.csv"
    hourly = compute_hourly(path)
    print("tunti,kwh")
    for hour, kwh in hourly:
        print(f"{hour.isoformat()},{kwh:.4f}")


if __name__ == "__main__":
    main()
