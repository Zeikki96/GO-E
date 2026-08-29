#!/usr/bin/env python3
"""
Muuntaa goe_log.csv-lokin aikasarjaksi (kWh per bucket) Suomen
paikallisajassa (Europe/Helsinki), kesä-/talviaika huomioiden.
Tukee sekä tuntikohtaista (60 min) että varttikohtaista (15 min)
bucket-kokoa - sama DST-turvallinen menetelmä molemmille.

MENETELMÄ (tarkka, ei approksimoitu):
go-e:n "lifetime_energy_kwh" (API-kenttä eto) on laturin elinikäinen,
aina kasvava kokonaisenergialaskuri - se ei nollaudu koskaan. Kahden
peräkkäisen mittauksen EROTUS kertoo täsmälleen paljonko energiaa kului
niiden välissä.

MIKSI VARTTITARKKUUS ON TÄRKEÄ:
Suomi siirtyi 1.10.2025 varttikohtaiseen sähkömarkkinaan, ja sähköyhtiöt
laskuttavat todellisen varttikohtaisen kulutuksen ja -hinnan mukaan
("kulutuspainotettu" hinta) - ei tunnin sisäisten varttien tasapainoista
keskiarvoa. Jos kulutus (esim. auton lataus) painottuu tunnin sisällä
tietylle halvalle/kalliille vartille, tuntitason arvio poikkeaa
todellisesta laskutuksesta. Varttitarkkuudella laskettu kustannus
vastaa siis paremmin oikeaa sähkölaskua.

AIKAVYÖHYKE JA TÄRKEÄ TOTEUTUSHUOMIO:
Kaikki KESTON/EROTUKSEN laskenta tehdään UTC-ajassa (yksiselitteinen).
Bucketin RAJAT lasketaan Suomen paikallisessa ajassa (zoneinfo), jotta
tulos vastaa pörssisähkön hintadataa. Ei vähennetä kahta paikallisaikaista
datetime-oliota suoraan toisistaan, koska Python käsittelee saman
tzinfo-olion aikaleimojen erotuksen oletuksena "naiivina" kellonaika-
aritmetiikkana eikä ota huomioon fold-arvoa (PEP 495) - tämä antaisi
virheellisen tuloksen DST-siirtymän yli. Siksi erotukset tehdään aina
UTC:ssa, ja paikallinen bucket-raja johdetaan vasta astimezone()-kutsulla.

Käyttö komentoriviltä:
    python3 laske_tuntikohtainen.py [polku/goe_log.csv] [--vartti]

Käyttö moduulina:
    from laske_tuntikohtainen import compute_hourly, compute_quarterly
    hourly = compute_hourly("goe_log.csv")      # 60 min bucketit
    quarterly = compute_quarterly("goe_log.csv") # 15 min bucketit
"""

import sys
import csv
from datetime import datetime, timedelta, timezone
from collections import defaultdict
from zoneinfo import ZoneInfo

MAX_GAP_HOURS = 2  # jos otosten väli on tätä pidempi, ohitetaan (esim. skripti ollut pois päältä)
HELSINKI = ZoneInfo("Europe/Helsinki")


def _local_bucket_bounds(utc_instant: datetime, tz: ZoneInfo, bucket_minutes: int):
    """Palauttaa (bucketin_alku_paikallisena, bucketin_alku_UTC, bucketin_loppu_UTC)
    UTC-hetkelle utc_instant. Kaikki rajavertailut tehdään UTC:ssa - vain
    bucket-avain on paikallinen."""
    local = utc_instant.astimezone(tz)
    if bucket_minutes == 60:
        bucket_start_local = local.replace(minute=0, second=0, microsecond=0)
    else:
        floored_minute = (local.minute // bucket_minutes) * bucket_minutes
        bucket_start_local = local.replace(minute=floored_minute, second=0, microsecond=0)
    bucket_start_utc = bucket_start_local.astimezone(timezone.utc)
    bucket_end_local = bucket_start_local + timedelta(minutes=bucket_minutes)  # naiivi kellonaika-askel, tarkoituksella
    bucket_end_utc = bucket_end_local.astimezone(timezone.utc)
    return bucket_start_local, bucket_start_utc, bucket_end_utc


def _compute_bucketed(path: str, bucket_minutes: int, tz: ZoneInfo = HELSINKI):
    rows = []
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            ts = datetime.fromisoformat(r["timestamp"]).astimezone(timezone.utc)
            r["timestamp"] = ts
            r["lifetime_energy_kwh"] = float(r["lifetime_energy_kwh"])
            rows.append(r)

    rows.sort(key=lambda r: r["timestamp"])

    bucket_kwh = defaultdict(float)

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
            bucket_start_local, bucket_start_utc, bucket_end_utc = _local_bucket_bounds(
                cursor, tz, bucket_minutes
            )
            segment_end = min(t1, bucket_end_utc)
            segment_seconds = (segment_end - cursor).total_seconds()  # UTC-UTC, turvallinen
            if segment_seconds <= 0:
                # Kevään kellonsiirtymän reunatapaus (paikallinen bucket ei etene) - hypätään eteenpäin
                cursor = bucket_end_utc
                continue
            share = segment_seconds / total_seconds
            bucket_kwh[bucket_start_local] += energy_diff * share
            cursor = segment_end

    return sorted(bucket_kwh.items(), key=lambda kv: kv[0].astimezone(timezone.utc))


def compute_hourly(path: str, tz: ZoneInfo = HELSINKI):
    """Palauttaa listan (tunnin_alkuaika, kwh) 60 min bucketeissa, Suomen ajassa."""
    return _compute_bucketed(path, 60, tz)


def compute_quarterly(path: str, tz: ZoneInfo = HELSINKI):
    """Palauttaa listan (vartin_alkuaika, kwh) 15 min bucketeissa, Suomen ajassa."""
    return _compute_bucketed(path, 15, tz)


def main():
    args = sys.argv[1:]
    use_quarter = "--vartti" in args
    args = [a for a in args if a != "--vartti"]
    path = args[0] if args else "goe_log.csv"

    if use_quarter:
        data = compute_quarterly(path)
        print("vartti_suomen_aikaa,kwh")
    else:
        data = compute_hourly(path)
        print("tunti_suomen_aikaa,kwh")

    for hour, kwh in data:
        print(f"{hour.isoformat()},{kwh:.4f}")


if __name__ == "__main__":
    main()
