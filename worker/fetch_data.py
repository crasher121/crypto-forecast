import os
import time
import datetime
import requests
from db import get_conn

CG = "https://api.coingecko.com/api/v3"
CMC ="https://pro-api.coinmarketcap.com/v1/cryptocurrency/quotes/latest"


def _floor_hour(dt):
    return dt.replace(minute=0, second=0, microsecond=0)


# первичный сид истории  тянем 90 дней почасовых цен с коингеко
def seed_history(symbol, cg_id):
    print("seeding history for", symbol)
    url = CG + "/coins/" + cg_id + "/market_chart"
    r = requests.get(url, params={"vs_currency": "usd", "days": "90"},timeout=60)
    data = r.json()
    prices = data.get("prices", [])
    vols = dict((int(x[0]), x[1]) for x in data.get("total_volumes",[]))
    caps = dict((int(x[0]), x[1]) for x in data.get("market_caps",[]))

    conn = get_conn()
    cur = conn.cursor()
    n = 0
    for ts_ms, price in prices:
        dt = datetime.datetime.utcfromtimestamp(ts_ms / 1000.0)
        dt = _floor_hour(dt)
        v = vols.get(int(ts_ms))
        c = caps.get(int(ts_ms))
        cur.execute("insert into prices(symbol,ts,price_usd,volume_24h,market_cap,source) values(%s,%s,%s,%s,%s,%s) on conflict (symbol,ts) do nothing",
                    (symbol, dt, price, v, c, "coingecko"))
        n = n + 1
    conn.commit()
    cur.close()
    conn.close()
    print("seeded rows:", n)
    time.sleep(2)  # шоб не словить рейтлимит коингеко


#3живой апдейт текущей цены
def fetch_live(pairs):
    key = os.environ.get("CMC_API_KEY", "").strip()
    now = _floor_hour(datetime.datetime.utcnow())

    if key == "":
        #фолбэк без ключа cmc - берем цену с бесплатного coingecko
        ids = ",".join([p[1] for p in pairs])
        r = requests.get(CG + "/simple/price", params={"ids": ids, "vs_currencies": "usd", "include_24hr_vol": "true", "include_market_cap": "true"}, timeout=30)
        d = r.json()
        conn = get_conn()
        cur = conn.cursor()
        for sym, cg_id in pairs:
            row = d.get(cg_id, {})
            price = row.get("usd")
            if price is None:
                continue
            cur.execute("insert into prices(symbol,ts,price_usd,volume_24h,market_cap,source) values(%s,%s,%s,%s,%s,%s) on conflict (symbol,ts) do update set price_usd=excluded.price_usd, volume_24h=excluded.volume_24h, market_cap=excluded.market_cap",
                        (sym, now, price, row.get("usd_24h_vol"), row.get("usd_market_cap"), "coingecko_live"))
        conn.commit()
        cur.close()
        conn.close()
        print("live update via coingecko done")
        return

    # боевой путь через коин маркет кап
    syms = ",".join([p[0] for p in pairs])
    headers = {"X-CMC_PRO_API_KEY": key}
    r = requests.get(CMC, params={"symbol": syms, "convert": "USD"}, headers=headers, timeout=30)
    d = r.json().get("data", {})
    conn = get_conn()
    cur = conn.cursor()
    for sym, cg_id in pairs:
        try:
            q = d[sym]["quote"]["USD"]
        except:
            continue
        cur.execute("insert into prices(symbol,ts,price_usd,volume_24h,market_cap,source) values(%s,%s,%s,%s,%s,%s) on conflict (symbol,ts) do update set price_usd=excluded.price_usd, volume_24h=excluded.volume_24h, market_cap=excluded.market_cap",
                    (sym, now, q.get("price"), q.get("volume_24h"), q.get("market_cap"), "cmc"))
    conn.commit()
    cur.close()
    conn.close()
    print("live update via cmc done")
