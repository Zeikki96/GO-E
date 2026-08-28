#!/usr/bin/env python3
"""
Luo yhteenvetokaavion ja päivittää README.md:n merkittyyn kohtaan.

Tämä ajetaan GitHub Actionsissa jokaisen pollauksen jälkeen. Se:
  1. Laskee tuntikohtaisen energian (laske_tuntikohtainen.compute_hourly)
  2. Piirtää kaavion viimeisten 14 vuorokauden päivittäisistä summista
  3. Kirjoittaa lyhyen tilastoyhteenvedon
  4. Korvaa README.md:ssä <!-- SUMMARY_START --> ... <!-- SUMMARY_END -->
     -kohdan tuoreella sisällöllä (loppuosa README:sta pysyy koskemattomana)

Käyttö:
    python3 update_summary.py
"""

import sys
from datetime import datetime, timedelta
from collections import defaultdict

import matplotlib
matplotlib.use("Agg")  # ei tarvitse näyttöä (headless CI-ympäristö)
import matplotlib.pyplot as plt

from laske_tuntikohtainen import compute_hourly

LOG_PATH = "goe_log.csv"
CHART_PATH = "summary_chart.png"
README_PATH = "README.md"
MARKER_START = "<!-- SUMMARY_START -->"
MARKER_END = "<!-- SUMMARY_END -->"

DAYS_TO_SHOW = 14


def build_daily_totals(hourly):
    daily = defaultdict(float)
    for hour, kwh in hourly:
        daily[hour.date()] += kwh
    return dict(sorted(daily.items()))


def draw_chart(daily_totals: dict, path: str):
    if not daily_totals:
        return False

    days = list(daily_totals.keys())[-DAYS_TO_SHOW:]
    values = [daily_totals[d] for d in days]
    labels = [d.strftime("%d.%m") for d in days]

    plt.figure(figsize=(9, 4))
    plt.bar(labels, values, color="#2f81f7")
    plt.title(f"Ladattu energia / vrk (viimeiset {len(days)} pv)")
    plt.ylabel("kWh")
    plt.xticks(rotation=45, ha="right")
    plt.tight_layout()
    plt.savefig(path, dpi=120)
    plt.close()
    return True


def build_summary_markdown(hourly, chart_exists: bool) -> str:
    if not hourly:
        return (
            f"{MARKER_START}\n"
            "### 📊 Latausdatan yhteenveto\n\n"
            "_Ei vielä riittävästi dataa yhteenvedon laskemiseen "
            "(tarvitaan vähintään kaksi mittausta)._\n"
            f"{MARKER_END}"
        )

    total_kwh = sum(kwh for _, kwh in hourly)
    first_hour = hourly[0][0]
    last_hour = hourly[-1][0]
    span_days = (last_hour - first_hour).total_seconds() / 86400

    # viimeisen 24h ja 7vrk summat
    now = last_hour
    last_24h = sum(kwh for h, kwh in hourly if h > now - timedelta(hours=24))
    last_7d = sum(kwh for h, kwh in hourly if h > now - timedelta(days=7))

    updated_at = datetime.now().astimezone().strftime("%d.%m.%Y klo %H:%M (%Z)")

    lines = [
        MARKER_START,
        "### 📊 Latausdatan yhteenveto",
        "",
        f"_Päivitetty automaattisesti: {updated_at}_",
        "",
        "_Energialukujen skaalaus kalibroitiin 28.8.2026 tunnettua "
        "mittarilukemaa vasten (ks. goe_logger.py:n kommentit)._",
        "",
        f"- **Yhteensä ladattu:** {total_kwh:.1f} kWh ({first_hour.strftime('%d.%m.%Y')} – {last_hour.strftime('%d.%m.%Y')})",
        f"- **Viimeiset 24 h:** {last_24h:.2f} kWh",
        f"- **Viimeiset 7 vrk:** {last_7d:.2f} kWh",
    ]

    if span_days >= 1:
        avg_per_day = total_kwh / span_days
        lines.append(f"- **Keskiarvo / vrk:** {avg_per_day:.2f} kWh")
    else:
        lines.append(
            f"- **Keskiarvo / vrk:** _lasketaan kun dataa on kertynyt vähintään vuorokausi "
            f"(nyt {span_days*24:.1f} h)_"
        )

    lines.append("")

    if chart_exists:
        lines.append(f"![Latausdata]({CHART_PATH})")
        lines.append("")

    lines.append(
        "_Tarkka tuntikohtainen data: [`tuntikohtainen.csv`](./tuntikohtainen.csv). "
        "Raakadata: [`goe_log.csv`](./goe_log.csv)._"
    )
    lines.append(MARKER_END)

    return "\n".join(lines)


def update_readme(summary_md: str):
    try:
        with open(README_PATH, "r", encoding="utf-8") as f:
            content = f.read()
    except FileNotFoundError:
        content = "# go-e Charger -looginen loki\n\n"

    if MARKER_START in content and MARKER_END in content:
        pre = content.split(MARKER_START)[0]
        post = content.split(MARKER_END)[1]
        new_content = pre + summary_md + post
    else:
        # Ei vielä merkkejä README:ssa -> lisätään loppuun
        new_content = content.rstrip() + "\n\n" + summary_md + "\n"

    with open(README_PATH, "w", encoding="utf-8") as f:
        f.write(new_content)


def main():
    try:
        hourly = compute_hourly(LOG_PATH)
    except FileNotFoundError:
        hourly = []

    daily_totals = build_daily_totals(hourly)
    chart_exists = draw_chart(daily_totals, CHART_PATH)

    summary_md = build_summary_markdown(hourly, chart_exists)
    update_readme(summary_md)

    # Kirjoitetaan myös tuntikohtainen.csv talteen (helppo ladata/analysoida erikseen)
    with open("tuntikohtainen.csv", "w", encoding="utf-8") as f:
        f.write("tunti,kwh\n")
        for hour, kwh in hourly:
            f.write(f"{hour.isoformat()},{kwh:.4f}\n")

    print(f"Päivitetty: {README_PATH}, {CHART_PATH if chart_exists else '(ei kaaviota)'}, tuntikohtainen.csv")


if __name__ == "__main__":
    main()
