-- инитим базу -запускается один раз при создании тома постгресаz 

create table if not exists pairs (
    symbol text primary key,
    name text,
    coingecko_id text,
    is_active boolean default true
);

create table if not exists prices (
    id serial primary key,
    symbol text references pairs(symbol),
    ts timestamptz not null,
    price_usd double precision,
    volume_24h double precision,
    market_cap double precision,
    source text,
    inserted_at timestamptz default now(),
    unique(symbol,ts))  ;

create table if not exists models (
    id serial primary key,
    symbol text references pairs(symbol),
    version integer,
    trained_at timestamptz default now(),
    rmse double precision,
    mae double precision,
    params text,
    artifact_path text
);

create table if not exists forecasts (
    id serial primary key,
    symbol text,
    model_version integer,
    run_ts timestamptz default now(),
    horizon_days integer,
    forecast_ts timestamptz,
    step integer,
    yhat double precision,
    yhat_lower double precision,
    yhat_upper double precision );

-- беерем топ-5 пар к юсд
insert into pairs(symbol,name,coingecko_id,is_active) values
    ('BTC','Bitcoin','bitcoin', true),
    ('ETH','Ethereum','ethereum', true),
    ('BNB','BNB','binancecoin', true),
    ('SOL','Solana','solana', true),
    ('XRP','XRP','ripple', true)
on conflict  (symbol) do nothing;
