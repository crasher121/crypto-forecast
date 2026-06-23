# Crypto Forecast — прогноз курсов криптовалют (ML + SARIMA)

Студенческий проект: FastAPI-сервис как обвязка над ML-моделью, PostgreSQL,
фоновый сборщик данных и веб-интервфейс на Streamlit. Прогнозирует курсы топ-5
валютных пар к USD (BTC, ETH, BNB, SOL, XRP) с помощью связки **SARIMA +
RandomForest по остаткам**.

## Архитектура

```
CoinMarketCap (live) + CoinGecko (история)
            │
            ▼
        worker (APScheduler)
   ingest / forecast-snapshot / weekly auto-tune
            │                       │
            ▼                       ▼
        PostgreSQL            models volume (*.pkl)
            │                       │
            ▼                       │
        FastAPI  ◄──────────────────┘
            │
            ▼
        Streamlit (свечной график + прогноз)
```

### Сервисы
- **db** — PostgreSQL, таблицы `pairs / prices / forecasts / models` (см. `db/init.sql`).
- **worker** — планировщик: раз в час тянет цену, раз в 2 часа пишет снапшот
  прогноза, **раз в неделю** переобучает модели. На первом старте сидит историю
  и делает первичное обучение.
- **api** — FastAPI, обвязка модели: `/pairs`, `/history`, `/forecast`,
  `/model/info`, `/forecast/history`, `/retrain`, `/health`.
- **web** — Streamlit: выбор пары, горизонт прогноза, свечной график как на
  TradingView + линия прогноза с доверительным интервалом.

## Запуск

```bash
cp .env.example .env
# по желанию вписать CMC_API_KEY (без него работает фолбэк на coingecko)
docker compose up --build
```

- Веб-морда: http://localhost:8501
- API (Swagger): http://localhost:8000/docs

> ⚠️ На первом старте worker сидит ~90 дней истории и обучает 5 моделей —
> это занимает пару минут. Если в Streamlit «нет данных» — подождите и обновите
> страницу.

## Про данные
Бесплатный CoinMarketCap отдаёт только текущие котировки, поэтому исторический
ряд для обучения один раз подгружается с CoinGecko, а дальше БД копит живые
данные. Прогнозы, сделанные в разное время суток, отличаются: живой ingest
обновляет текущий день, и точка отсчёта модели смещается.
