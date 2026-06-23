import os
import pickle
import datetime
import numpy as np
import pandas as pd
from statsmodels.tsa.statespace.sarimax import SARIMAX
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_squared_error, mean_absolute_error
from db import get_conn

MODELS_DIR="/models"
N_LAGS=7                       # сколько прошлых остатков кидаем в лес
SARIMA_ORDER = (1,1,1)
SARIMA_SEASONAL = (1, 0,1,7 )   #недельная сезонность по дням


#тянем дневной ряд (часовые цены -> закрыта цена по дням)
def load_daily_series(symbol):
    conn =get_conn()
    cur =conn.cursor()
    cur.execute("select ts, price_usd from prices where symbol=%s order by ts",(symbol,))
    rows = cur.fetchall()
    cur.close()
    conn.close()
    if len(rows) == 0:
        return None
    df = pd.DataFrame(rows, columns=["ts", "price"])
    df["ts"]=pd.to_datetime(df["ts"])
    df =  df.set_index("ts").sort_index()
    s =df["price"].resample("D").last().dropna()
    
    return s


def _make_lag_matrix(resid):
    X = []
    y=[]
    r=list(resid)
    for i in range(N_LAGS, len(r)):
        X.append(r[i - N_LAGS:i])
        y.append(r[i])
    return np.array(X), np.array(y)


# обучение модели на одной паре
def train(symbol):
    s = load_daily_series(symbol)
    if s is None or len(s) < 40:
        print("not enough data for", symbol)
        return None

    # 1 -sarima на дневном ряде
    model = SARIMAX(s.values, order=SARIMA_ORDER, seasonal_order=SARIMA_SEASONAL,
                    enforce_stationarity=False, enforce_invertibility=False)
    res = model.fit(disp=False)
    fitted = res.fittedvalues
    resid = s.values - fitted

    # 2 - лес по остаткам (тут и есть связка ML + sarimA)
    X, y = _make_lag_matrix(resid)
    rf = RandomForestRegressor(n_estimators=50, random_state=42)
    used_rf = False
    if len(X)>10:
        rf.fit(X,y)
        used_rf = True

    # метрики гибрида на обучающей выборке (бтв для проекта сойдет)
    hybrid_fit = fitted.copy()
    if used_rf:
        pred_resid = rf.predict(X)
        hybrid_fit[N_LAGS:] =fitted[N_LAGS:]+pred_resid
    rmse= float(np.sqrt(mean_squared_error(s.values, hybrid_fit)))
    mae=float(mean_absolute_error(s.values, hybrid_fit))

    conn = get_conn()
    cur = conn.cursor()
    cur.execute("select coalesce(max(version),0) from models where symbol=%s", (symbol,))
    ver = cur.fetchone()[0] + 1

    path = MODELS_DIR + "/" + symbol + "_latest.pkl"
    bundle = {"sarima": res,"rf": rf, "used_rf": used_rf,
              "last_resid":list(resid[-N_LAGS:]),"n_lags": N_LAGS,
              "last_ts": str(s.index[-1]), "version": ver}
    
    with open(path, "wb") as f:
        pickle.dump(bundle, f)

    cur.execute("insert into models(symbol,version,rmse,mae,params,artifact_path) values(%s,%s,%s,%s,%s,%s)",
                (symbol, ver, rmse, mae, str(SARIMA_ORDER) + "x" + str(SARIMA_SEASONAL), path))
    
    conn.commit()
    cur.close()
    conn.close()
    print("trained", symbol, "v", ver, "rmse", round(rmse, 2))
    return ver


# прогноз на horizon_days дней вперёд
def make_forecast(symbol, horizon_days, store):
    path = MODELS_DIR + "/" + symbol + "_latest.pkl"
    if not os.path.exists(path):
        return None
    with open(path, "rb") as f:
        bundle = pickle.load(f)

    s = load_daily_series(symbol)
    if s is None:
        return None

    res = bundle["sarima"]
    ##дотягиваем модель свежими наблюдениями без переобучения параметров
    # именно поэтому прогноз в 13:00 и 15:00 разный
    last_ts = pd.to_datetime(bundle["last_ts"])
    new_part = s[s.index > last_ts]
    if len(new_part) > 0:
        try:
            res = res.append(new_part.values, refit=False)
        except:
            pass

    fc = res.get_forecast(steps=horizon_days)
    mean = np.array(fc.predicted_mean)
    ci = np.array(fc.conf_int(alpha=0.2))   #80 проц интервал
    lower = ci[:,0]
    upper = ci[:,1]

    # лес добавляет прогноз остатков рекусивно
    rf = bundle["rf"]
    used = bundle["used_rf"]
    n_lags = bundle["n_lags"]
    lags = list(bundle["last_resid"])
    add = []
    for i in range(horizon_days):
        if used:
            p = float(rf.predict([lags[-n_lags:]])[0])
        else:
            p = 0.0
        add.append(p)
        lags.append(p)
    add= np.array(add)
    mean= mean + add
    lower=lower+add
    upper = upper + add

    start = s.index[-1]
    out = []
    for i in range(horizon_days):
        d = start + pd.Timedelta(days=i + 1)
        out.append({"forecast_ts": str(d.date()), "step": i + 1,
                    "yhat": float(mean[i]), "yhat_lower": float(lower[i]), "yhat_upper": float(upper[i])})

    if store:
        _store_forecast(symbol, bundle["version"], horizon_days, out)
    return {"symbol": symbol, "version": bundle["version"], "forecast": out}


def _store_forecast(symbol, version, horizon_days, out):
    conn = get_conn()
    cur = conn.cursor()
    
    for row in out:
        cur.execute("insert into forecasts(symbol,model_version,horizon_days,forecast_ts,step,yhat,yhat_lower,yhat_upper) values(%s,%s,%s,%s,%s,%s,%s,%s)",
                    (symbol, version, horizon_days, row["forecast_ts"], row["step"], row["yhat"], row["yhat_lower"], row["yhat_upper"]))
    conn.commit()
    cur.close()
    conn.close()
