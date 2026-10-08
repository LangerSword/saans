import json, sys, urllib.request
sys.path.insert(0, "src")
from core import rules

URL = ("https://air-quality-api.open-meteo.com/v1/air-quality"
       "?latitude=28.6448&longitude=77.2167"
       "&hourly=pm2_5,pm10,us_aqi&timezone=Asia%2FKolkata&forecast_days=1")
d = json.load(urllib.request.urlopen(URL, timeout=25))
h = d["hourly"]
print(f"{'time':17} {'pm2_5':>7} {'pm10':>6} {'us_aqi':>7} {'CPCB':>6} {'tier(US)':>9} {'tier(CPCB)':>11}  verdict")
print("-"*88)
mis = tot = 0
for i,t in enumerate(h["time"]):
    pm, p10, us = h["pm2_5"][i], h["pm10"][i], h["us_aqi"][i]
    if None in (pm,p10,us): continue
    cpcb,_ = rules.aqi_from_pm(pm, p10)
    tu, tc = rules.aqi_to_band(us), rules.aqi_to_band(cpcb)
    tot += 1; bad = tu != tc; mis += bad
    print(f"{t:17} {pm:7.1f} {p10:6.1f} {us:7.1f} {cpcb:6.1f} {tu:>9} {tc:>11}  {'WRONG' if bad else ''}")
print("-"*88)
print(f"{tot} hours, {mis} would be misclassified by us_aqi ({100*mis//tot}%)")
