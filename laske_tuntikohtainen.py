#!/usr/bin/env python3
"""
Muuntaa goe_log.csv-lokin tuntikohtaiseksi energiankulutukseksi (kWh/tunti)
Suomen paikallisajassa (Europe/Helsinki), kesä-/talviaika huomioiden.

MENETELMÄ (tarkka, ei approksimoitu):
go-e:n "lifetime_energy_kwh" (API-kenttä eto) on laturin elinikäinen,
aina kasvava kokonaisenergialaskuri - se ei nollaudu koskaan. Kahden
peräkkäisen mittauksen EROTUS kertoo täsmälleen paljonko energiaa kului
niiden välissä.

AIKAVYÖHYKE JA TÄRKEÄ TOTEUTUSHUOMIO:
Kaikki KESTON/EROTUKSEN laskenta tehdään UTC-ajassa (yksiselitteinen,
ei koskaan moniselitteinen). Tuntibucketin RAJAT lasketaan Suomen
paikallisessa ajassa (Europe/Helsinki, zoneinfo-moduulilla), jotta
tulos vastaa samaa "tuntia" kuin pörssisähkön hintadata.

Tätä ei tehdä suoraan vähentämällä kahta paikallisaikaista datetime-
oliota toisistaan, koska Python käsittelee saman aikavyöhykeolion
(tzinfo) omaavien datetime-olioiden erotuksen/vertailun OLETUSARVOISESTI
"naiivina" kellonaika-aritmetiikkana, joka EI ota huomioon fold-arvoa
(PEP 495) - tämä antaisi virheellisen (usein nollan) tuloksen DST-
siirtymän yli laskettaessa. Siksi erotukset/vertailut tehdään aina
UTC-ajassa, ja paikallinen tunti johdetaan vasta astimezone()-kutsulla
kunkin pisteen kohdalla erikseen.

HUOM kahdesta erikoispäivästä vuodessa (testattu, ks. testit):
- Kevään kellojen siirto: se paikallinen tunti jota ei ole olemassa
  (esim. 03:00-04:00) ei tuota omaa riviä - energia jakautuu oikein
  ympäröiviin tunteihin. Kokonaisenergia säilyy oikeana.
- Syksyn kellojen siirto: sama kellonaika (esim. 03:00) esiintyy
  todellisuudessa kahdesti (ensin kesäajassa, sitten talviajassa).
  Tämä toteutus YHDISTÄÄ ne yhdeksi kahden tunnin mittaiseksi riviksi
  sen sijaan että erottelisi ne kahdeksi tuntiriviksi - kokonaisenergia
  on silti oikein, dataa ei katoa eikä tuplaannu. Jos tarvitset joskus
  näiden kahden tunnin erottelun (esim. tarkkaan pörssisähkön "3A"/"3B"
  -hintavertailuun), tämä yksi tunti vuodessa vaatisi lisäkäsittelyn.

Käyttö komentoriviltä:
    python3 laske_tuntikohtainen.py [polku/goe_log.csv]

Käyttö moduulina (esim. update_summary.py):
    from laske_tuntikohtainen import compute_hourly
    hourly = compute_hourly("goe_log.csv")  # -> list of (datetime, kwh) Suomen ajassa
"""

import sys
import csv
from datetime import datetime, timedelta, timezone
from collections import defaultdict
from zoneinfo import ZoneInfo

MAX_GAP_HOURS = 2  # jos otosten väli on tätä pidempi, ohitetaan (esim. skripti ollut pois päältä)
HELSINKI = ZoneInfo("Europe/Helsinki")


def _local_hour_bounds(utc_instant: datetime, tz: ZoneInfo):
    """Palauttaa (tunnin_alku_paikallisena, tunnin_alku_UTC, tunnin_loppu_UTC)
    UTC-hetkelle utc_instant. Kaikki rajavertailut tehdään UTC:ssa - vain
    bucket-avain on paikallinen."""
    local = utc_instant.astimezone(tz)
    hour_start_local = local.replace(minute=0, second=0, microsecond=0)
    hour_start_utc = hour_start_local.astimezone(timezone.utc)
    hour_end_local = hour_start_local + timedelta(hours=1)  # naiivi kellonaika-askel, tarkoituksella
    hour_end_utc = hour_end_local.astimezone(timezone.utc)
    return hour_start_local, hour_start_utc, hour_end_utc


def compute_hourly(path: str, tz: ZoneInfo = HELSINKI):
    """Palauttaa listan (tunnin_alkuaika: datetime, kwh: float) annetussa
    aikavyöhykkeessä (oletus Europe/Helsinki), aikajärjestyksessä."""
    rows = []
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            ts = datetime.fromisoformat(r["timestamp"]).astimezone(timezone.utc)
            r["timestamp"] = ts
            r["lifetime_energy_kwh"] = float(r["lifetime_energy_kwh"])
            rows.append(r)

    rows.sort(key=lambda r: r["timestamp"])

    hourly_kwh = defaultdict(float)

    for i in range(1, len(rows)):
        prev, cur = rows[i - 1], rows[i]

        t0, t1 = prev["timestamp"], cur["timestamp"]  # molemmat UTC - turvallinen erotus
        dt = t1 - t0
        if dt <= timedelta(0) or dt > timedelta(hours=MAX_GAP_HOURS):
            continue

        energy_diff = cur["lifetime_energy_kwh"] - prev["lifetime_energy_kwh"]
        if energy_diff <= 0:
            continue

        total_seconds = dt.total_seconds()

        cursor = t0  # UTC koko ajan
        while cursor < t1:
            hour_start_local, hour_start_utc, hour_end_utc = _local_hour_bounds(cursor, tz)
            segment_end = min(t1, hour_end_utc)
            segment_seconds = (segment_end - cursor).total_seconds()  # UTC-UTC, turvallinen
            if segment_seconds <= 0:
                # Kevään kellonsiirtymän reunatapaus (paikallinen tunti ei etene) - hypätään eteenpäin
                cursor = hour_end_utc
                continue
            share = segment_seconds / total_seconds
            hourly_kwh[hour_start_local] += energy_diff * share
            cursor = segment_end

    return sorted(hourly_kwh.items(), key=lambda kv: kv[0].astimezone(timezone.utc))


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else "goe_log.csv"
    hourly = compute_hourly(path)
    print("tunti_suomen_aikaa,kwh")
    for hour, kwh in hourly:
        print(f"{hour.isoformat()},{kwh:.4f}")


if __name__ == "__main__":
    main()
