import os
import requests
import datetime
import pandas as pd
import streamlit as st
import plotly.graph_objects as go

API = os.environ.get("API_URL", "http://api:8000")

st.set_page_config(page_title="Прогноз криптовалют", layout="wide")
st.title("📈 Прогноз курсов криптовалют (ML + SARIMA)")

# тянем список пар
try:
    pairs = requests.get(API + "/pairs", timeout=10).json()
except Exception as e:
    st.error("API недоступен: " + str(e))
    st.stop()

sym_list = [p["symbol"] for p in pairs]
name_map = dict((p["symbol"], p["name"]) for p in pairs)

st.sidebar.header("Настройки")
symbol = st.sidebar.selectbox("Валютная пара", sym_list, format_func=lambda x: x + "/USD (" + str(name_map.get(x, "")) + ")")
horizon = st.sidebar.slider("Горизонт прогноза, дней", 7, 60, 14)
days_hist = st.sidebar.slider("Сколько истории показывать, дней", 30, 90, 90)

if st.sidebar.button("🔁 Переобучить модель"):
    requests.post(API + "/retrain", params={"symbol": symbol})
    st.sidebar.success("Запущено переобучение (займёт немного времени)")

# история цен
hist = requests.get(API + "/history", params={"symbol": symbol, "days": days_hist}).json()
if len(hist) == 0:
    st.warning("Нет данных по этой паре (worker ещё собирает). Загляните чуть позже.")
    st.stop()

df = pd.DataFrame(hist)
df["ts"] = pd.to_datetime(df["ts"])
df = df.set_index("ts").sort_index()

# дневные свечи из часовых цен
o =df["price"].resample("D").first()
h =df["price"].resample("D").max()
l= df["price"].resample("D").min()
c = df["price"].resample("D").last()
candles = pd.DataFrame({"open": o, "high": h, "low": l, "close": c}).dropna()

# прогноз
fc = requests.get(API + "/forecast", params={"symbol": symbol, "horizon_days": horizon, "store": True}).json()

fig = go.Figure()
fig.add_trace(go.Candlestick(x=candles.index, open=candles["open"], high=candles["high"],
                             low=candles["low"], close=candles["close"], name="История"))

if "forecast" in fc:
    f = pd.DataFrame(fc["forecast"])
    f["forecast_ts"] = pd.to_datetime(f["forecast_ts"])
    fig.add_trace(go.Scatter(x=f["forecast_ts"],y=f["yhat"],mode="lines",name="Прогноз",
                             line=dict(color="orange", width=2)
                             )
                            )
    fig.add_trace(go.Scatter(x=f["forecast_ts"], y=f["yhat_upper"],mode="lines",
                             line=dict(width=0),showlegend=False)
                             )
    fig.add_trace(go.Scatter(x=f["forecast_ts"],y =f["yhat_lower"], mode="lines", 
                             fill="tonexty",
                             fillcolor="rgba(255,165,0,0.2)",line=dict(width=0), 
                             name="Доверит. интервал"))
else:
    st.info("Модель ещё не обучена — подождите первичное обучение worker'а.")

fig.update_layout(height=600, xaxis_rangeslider_visible=False, template="plotly_dark")
st.plotly_chart(fig, use_container_width=True)

# инфо о модели
info = requests.get(API + "/model/info", params={"symbol": symbol}).json()
c1, c2, c3, c4 = st.columns(4)
if info.get("trained"):
    c1.metric("Версия модели", info["version"])
    c2.metric("RMSE", round(info["rmse"], 2))
    c3.metric("MAE", round(info["mae"], 2))
    c4.metric("Обучена", str(info["trained_at"])[:16])
else:
    st.write("Модель пока не обучена")

st.caption("Данные: CoinMarketCap (live) + CoinGecko (история). Модель: SARIMA + RandomForest по остаткам.")
