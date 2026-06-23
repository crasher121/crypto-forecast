import time
import datetime
from apscheduler.schedulers.background import BackgroundScheduler
import fetch_data
import train_model
from db import get_conn


def get_active_pairs():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("select symbol, coingecko_id from pairs where is_active=true order by symbol")
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return rows


# каждый час подтягиваем свежую цену
def job_ingest():
    print("[job] ingest", datetime.datetime.utcnow())
    pairs = get_active_pairs()
    try:
        fetch_data.fetch_live(pairs)
    except Exception as e:
        print("ingest error", e)


# каждые 2 часа - снапшот прогноза (чтоб копилась история предсказаний)
def job_forecast_snapshot():
    print("[job] forecast snapshot")
    for sym, cg in get_active_pairs():
        try:
            train_model.make_forecast(sym, 30, True)
        except Exception as e:
            print("forecast error", sym, e)


# раз в неделю - авто-тюн -- переобучаем на накопленных данных
def job_auto_tune():
    print("[job] weekly auto-tune")
    for sym, cg in get_active_pairs():
        try:
            train_model.train(sym)
        except Exception as e:
            print("train error", sym, e)


# первый запуск- сид истории плюс первичное обучение
def bootstrap():
    pairs = get_active_pairs()
    for sym,cg in pairs:
        conn= get_conn()
        cur = conn.cursor()
        cur.execute("select count(*) from prices where symbol=%s", (sym,))
        cnt =cur.fetchone()[0]
        cur.close()
        conn.close()
        if cnt==0:
            try:
                fetch_data.seed_history(sym, cg)
            except Exception as e:
                print("seed error", sym, e)
    for sym, cg in pairs:
        try:
            train_model.train(sym)
        except Exception as e:
            print("initial train error", sym, e)


if __name__ == "__main__":
    time.sleep(10)  # ждем пока бд точно поднимется и отработает init.sql
    print("worker starting...")
    bootstrap()

    sch = BackgroundScheduler()
    sch.add_job(job_ingest, "interval", hours=1, id="ingest")
    sch.add_job(job_forecast_snapshot, "interval", hours=2, id="snap")
    sch.add_job(job_auto_tune, "interval", weeks=1, id="tune")
    sch.start()
    print("scheduler started")

    while True:
        time.sleep(60)
