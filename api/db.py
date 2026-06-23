import os
import psycopg2

# подключение к базе (без пула, для студенческого проекта норм)
def get_conn():
    host=os.environ.get("POSTGRES_HOST", "db")
    db =os.environ.get("POSTGRES_DB", "crypto")
    u=os.environ.get("POSTGRES_USER", "postgres")
    p = os.environ.get("POSTGRES_PASSWORD", "postgres")
    port = os.environ.get("POSTGRES_PORT", "5432")
    conn = psycopg2.connect(host=host, dbname=db, user=u, password=p, port=port)
    return conn
