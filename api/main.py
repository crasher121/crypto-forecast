from fastapi import FastAPI, BackgroundTasks
from fastapi.responses import JSONResponse
import datetime
import train_model
from db import get_conn

app = FastAPI(title="Crypto Forecast API (student project)")


@app.get("/health")
def health():
    return {"status":"ok"}


@app.get("/pairs")
def pairs():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("select symbol, name, coingecko_id, is_active from pairs order by symbol")
    rows = cur.fetchall()
    cur.close()
    conn.close()
    res = []
    for r in rows:
        res.append({"symbol":r[0],"name":r[1],"coingecko_id":r[2],"is_active":r[3]})
    return res


@app.get("/history")
def history(symbol:str, days:int =90):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("select ts, price_usd, volume_24h from prices where symbol=%s and ts >= now() - make_interval(days => %s) order by ts", (symbol, days))
    rows = cur.fetchall()
    cur.close()
    conn.close()
    out = []
    for r in rows:
        out.append({"ts":str(r[0]), "price":r[1],"volume":r[2]})
    return out


@app.get("/forecast")
def forecast(symbol:str,horizon_days:int=14,store:bool=False):
    r = train_model.make_forecast(symbol,horizon_days,store)
    if r is None:
        return JSONResponse(status_code=404,content={"error":"model not trained yet"})
    return r


@app.get("/model/info")
def model_info(symbol: str):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("select version, trained_at, rmse, mae, params from models where symbol=%s order by version desc limit 1", (symbol,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    if row is None:
        return {"trained": False}
    return {"trained": True,"version":row[0], "trained_at":str(row[1]), "rmse":row[ 2],"mae": row[3], "params": row[4]}


@app.get("/forecast/history")
def forecast_history(symbol:str,limit:int=200):
    # последние сохранеенные прогнозы (видно как менялся прогноз в течение дня)
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("select run_ts, forecast_ts, yhat from forecasts where symbol=%s order by run_ts desc, step asc limit %s", (symbol, limit))
    rows = cur.fetchall()
    cur.close()
    conn.close()
    out = []
    
    for r in rows:
        out.append({"run_ts": str(r[0]), "forecast_ts": str(r[1]), "yhat": r[2]})
    return out


def _do_train(symbol):
    train_model.train(symbol)


@app.post("/retrain")
def retrain(symbol: str, bg: BackgroundTasks):
    bg.add_task(_do_train, symbol)
    return {"status": "training started", "symbol": symbol}
