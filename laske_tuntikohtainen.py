#!/usr/bin/env python3
"""
Muuntaa goe_log.csv-lokin tuntikohtaiseksi energiankulutukseksi (kWh/tunti).

Periaate: koska power_kw on hetkellinen teho joka POLL_INTERVAL_SECONDS
välein, kunkin mittauspisteen energiasisältö on
    power_kw * (aika edelliseen mittaukseen tunteina)
Nämä summataan tunneittain. Tämä on paljon tarkempi tapa kuin
sessiokohtaisen kWh:n approksimointi, koska nyt käytössä on oikea
mitattu teho jokaiselta pollausväliltä.

Käyttö:
    python3 laske_tuntikohtainen.py [polku/goe_log.csv]
"""

import sys
import csv
from datetime import datetime
from collections import defaultdict

def main():
    path = sys.argv[1] if len(sys.argv) > 1 else "goe_log.csv"

    rows = []
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            r["timestamp"] = datetime.fromisoformat(r["timestamp"])
            r["power_kw"] = float(r["power_kw"])
            rows.append(r)

    rows.sort(key=lambda r: r["timestamp"])

    hourly_kwh = defaultdict(float)

    for i in range(1, len(rows)):
        prev, cur = rows[i - 1], rows[i]
        dt_hours = (cur["timestamp"] - prev["timestamp"]).total_seconds() / 3600.0
        if dt_hours <= 0 or dt_hours > 1:
            # Ohitetaan epänormaalin pitkät (esim. skripti ollut pois päältä) välit,
            # ettei niistä synny valeenergiaa.
            continue
        # Käytetään edellisen mittauksen tehoa kuvaamaan koko väliä (yksinkertaistus)
        energy = prev["power_kw"] * dt_hours
        hour_bucket = prev["timestamp"].replace(minute=0, second=0, microsecond=0)
        hourly_kwh[hour_bucket] += energy

    print("tunti,kwh")
    for hour in sorted(hourly_kwh):
        print(f"{hour.isoformat()},{hourly_kwh[hour]:.4f}")


if __name__ == "__main__":
    main()
