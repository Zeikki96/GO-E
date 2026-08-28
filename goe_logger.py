#!/usr/bin/env python3
"""
go-e Charger -looginen loki

Pollaa go-e:n Cloud API:a säännöllisin väliajoin ja tallentaa tehon
ja ladatun energian aikaleimattuna CSV-tiedostoon. Tarkoitus: kerätä
riittävän tarkka aikasarja, jotta lataus voidaan myöhemmin yhdistää
pörssisähkön tuntihintoihin.

KÄYTTÖÖNOTTO
------------
1. Avaa go-e-sovellus -> Internet / Advanced Settings (tai vastaava)
   ja aktivoi "Cloud API". Kopioi sieltä laitteesi:
     - sarjanumero (serial number, 6-numeroinen)
     - API-token (cloud api key / "cak")
2. Kopioi config.example.json -> config.json ja täytä tiedot sinne.
   ÄLÄ kirjoita tokenia suoraan tähän tiedostoon.
3. Asenna riippuvuus:  pip install requests
4. Aja skripti jatkuvana taustaprosessina, esim.:
     python3 goe_logger.py
   tai systemd-palveluna / Windows-tehtävänä (ks. README.md).

TALLENNETTAVAT KENTÄT
----------------------
timestamp        - paikallinen aikaleima (ISO 8601)
car_state        - auton kytkentä-/lataustila (1=ei autoa, 2=lataa, 3=valmis+kytketty, 4=virhe)
power_kw         - hetkellinen kokonaisteho kilowatteina
session_energy_kwh - nykyisen lataussession ladattu energia (nollautuu uuden session alkaessa)
lifetime_energy_kwh - laturin koko elinkaaren aikana lataama energia (kasvaa aina)
"""

import json
import time
import csv
import os
import sys
from datetime import datetime, timezone
import urllib.request
import urllib.error

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.json")
LOG_PATH = os.path.join(os.path.dirname(__file__), "goe_log.csv")

POLL_INTERVAL_SECONDS = 60  # kuinka usein kysytään tilaa (jatkuvassa paikallisessa ajossa).

FILTER_KEYS = "nrg,dws,car,eto"


def load_config():
    """
    Lukee tunnukset kahdesta mahdollisesta lähteestä, tässä järjestyksessä:
      1. Ympäristömuuttujat GOE_SERIAL / GOE_TOKEN (käytössä GitHub Actionsissa,
         jossa nämä tulevat repon "Secrets"-asetuksista).
      2. config.json (käytössä paikallisessa jatkuvassa ajossa, esim. Raspberry Pi).
    """
    env_serial = os.environ.get("GOE_SERIAL")
    env_token = os.environ.get("GOE_TOKEN")
    if env_serial and env_token:
        return {
            "serial": env_serial,
            "token": env_token,
            "poll_interval_seconds": int(
                os.environ.get("GOE_POLL_INTERVAL_SECONDS", POLL_INTERVAL_SECONDS)
            ),
        }

    if not os.path.exists(CONFIG_PATH):
        sys.exit(
            "Tunnuksia ei löytynyt.\n"
            "Joko aseta ympäristömuuttujat GOE_SERIAL ja GOE_TOKEN, "
            "tai kopioi config.example.json -> config.json ja täytä serial + token."
        )
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    if not cfg.get("serial") or not cfg.get("token"):
        sys.exit("config.json: 'serial' ja 'token' pitää olla täytetty.")
    return cfg


def fetch_status(serial: str, token: str) -> dict:
    url = (
        f"https://{serial}.api.v3.go-e.io/api/status"
        f"?token={token}&filter={FILTER_KEYS}"
    )
    req = urllib.request.Request(url, headers={"User-Agent": "goe-logger/1.0"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        if resp.status != 200:
            raise RuntimeError(f"Odottamaton HTTP-status: {resp.status}")
        return json.loads(resp.read().decode("utf-8"))


def parse_status(data: dict) -> dict:
    nrg = data.get("nrg", [0] * 16)
    # nrg[11] = kokonaisteho yksikössä 0.01 kW
    power_kw = (nrg[11] if len(nrg) > 11 else 0) / 100.0

    # dws = nykyisen session energia deca-watt-sekunteina (1 dws = 10 Ws)
    dws = int(data.get("dws", 0))
    session_energy_kwh = (dws * 10) / 3_600_000.0

    # eto = laturin elinikäinen kokonaisenergia yksikössä 0.1 kWh
    eto = int(data.get("eto", 0))
    lifetime_energy_kwh = eto / 10.0

    car_state = data.get("car", "")

    return {
        "timestamp": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "car_state": car_state,
        "power_kw": round(power_kw, 3),
        "session_energy_kwh": round(session_energy_kwh, 4),
        "lifetime_energy_kwh": round(lifetime_energy_kwh, 3),
    }


def append_row(row: dict):
    file_exists = os.path.exists(LOG_PATH)
    with open(LOG_PATH, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(row.keys()))
        if not file_exists:
            writer.writeheader()
        writer.writerow(row)


def poll_once(cfg: dict) -> bool:
    """Tekee yhden kyselyn ja lisää rivin lokiin. Palauttaa True onnistuessa."""
    try:
        data = fetch_status(cfg["serial"], cfg["token"])
        row = parse_status(data)
        append_row(row)
        print(row)
        return True
    except urllib.error.HTTPError as e:
        print(f"HTTP-virhe ({e.code}): laturi voi olla offline tai token väärä.")
    except urllib.error.URLError as e:
        print(f"Verkkovirhe: {e}")
    except Exception as e:
        print(f"Odottamaton virhe: {e}")
    return False


def main():
    cfg = load_config()

    # --once: yksi kysely ja poistu. Tätä käyttää GitHub Actions -workflow,
    # joka kutsuu skriptiä ajastetusti sen sijaan että skripti pyörisi itse silmukassa.
    once_mode = "--once" in sys.argv or os.environ.get("GITHUB_ACTIONS") == "true"

    if once_mode:
        ok = poll_once(cfg)
        sys.exit(0 if ok else 1)

    interval = cfg.get("poll_interval_seconds", POLL_INTERVAL_SECONDS)
    print(f"go-e logger käynnissä. Kirjoitetaan lokiin: {LOG_PATH}")
    print(f"Pollausväli: {interval}s. Pysäytä Ctrl+C:llä.")

    while True:
        poll_once(cfg)
        time.sleep(interval)


if __name__ == "__main__":
    main()
