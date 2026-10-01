CREATE SCHEMA IF NOT EXISTS trade;
CREATE TABLE trade.users (
 id text PRIMARY KEY, email text NOT NULL UNIQUE, role text NOT NULL CHECK(role IN ('USER','ADMIN','SUPERUSER')),
 password_hash text, created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE trade.sessions (token_hash text PRIMARY KEY, user_id text REFERENCES trade.users(id), expires_at timestamptz NOT NULL);
CREATE TABLE trade.reset_tokens (token_hash text PRIMARY KEY, user_id text REFERENCES trade.users(id), expires_at timestamptz NOT NULL, used boolean NOT NULL DEFAULT false);
CREATE TABLE trade.controls (
 id int PRIMARY KEY CHECK(id=1), kill_switch boolean NOT NULL DEFAULT false, live_armed boolean NOT NULL DEFAULT false,
 risk jsonb NOT NULL, updated_at timestamptz NOT NULL DEFAULT now()
);
INSERT INTO trade.controls VALUES (1,false,false,'{"max_order_value":10000,"max_quantity":100,"max_position_value":50000,"max_daily_capital":25000,"max_open_orders":5,"max_quote_age_seconds":30,"allowed_instruments":["NIFTYBEES","GOLDBEES"],"allowed_brokers":["DUMMY"],"allowed_accounts":["paper"],"market_hours_only":true}',now());
CREATE TABLE trade.brokers (
 id text PRIMARY KEY, account_id text NOT NULL, enabled boolean NOT NULL DEFAULT false, cash numeric(18,2) NOT NULL DEFAULT 100000,
 scenario text NOT NULL DEFAULT 'NORMAL' CHECK(scenario IN ('NORMAL','REJECT','PARTIAL','OUTAGE','AMBIGUOUS'))
);
INSERT INTO trade.brokers(id,account_id,enabled) VALUES ('DUMMY','paper',true),('DHAN','unconfigured',false),('FYERS','unconfigured',false),('SHOONYA','unconfigured',false),('ZERODHA','unconfigured',false);
CREATE TABLE trade.quotes (symbol text PRIMARY KEY, price numeric(18,4) NOT NULL CHECK(price>0), updated_at timestamptz NOT NULL DEFAULT now());
INSERT INTO trade.quotes(symbol,price) VALUES ('NIFTYBEES',250),('GOLDBEES',75);
CREATE TABLE trade.strategies (
 id text PRIMARY KEY, owner_id text REFERENCES trade.users(id), name text NOT NULL, broker text REFERENCES trade.brokers(id), account_id text NOT NULL,
 symbol text NOT NULL, budget numeric(18,2) NOT NULL CHECK(budget>0), limit_price numeric(18,4),
 enabled boolean NOT NULL DEFAULT false, schedule_time text, last_run_at timestamptz, created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE trade.runs (
 id text PRIMARY KEY, strategy_id text REFERENCES trade.strategies(id), idempotency_key text NOT NULL UNIQUE,
 status text NOT NULL CHECK(status IN ('STARTED','COMPLETED','REJECTED','AMBIGUOUS','SKIPPED')), reason text,
 started_at timestamptz NOT NULL DEFAULT now(), finished_at timestamptz
);
CREATE TABLE trade.orders (
 id text PRIMARY KEY, run_id text REFERENCES trade.runs(id), strategy_id text REFERENCES trade.strategies(id), owner_id text REFERENCES trade.users(id),
 broker text NOT NULL, account_id text NOT NULL, broker_order_id text, symbol text NOT NULL, side text NOT NULL CHECK(side IN ('BUY','SELL')),
 quantity int NOT NULL CHECK(quantity>0), filled_quantity int NOT NULL DEFAULT 0, price numeric(18,4) NOT NULL,
 order_type text NOT NULL CHECK(order_type IN ('MARKET','LIMIT')), limit_price numeric(18,4),
 status text NOT NULL CHECK(status IN ('CREATED','SUBMITTING','OPEN','PARTIAL','FILLED','REJECTED','CANCELLED','AMBIGUOUS')),
 reason text, created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE trade.positions (
 broker text NOT NULL, account_id text NOT NULL, symbol text NOT NULL, owner_id text REFERENCES trade.users(id),
 quantity int NOT NULL DEFAULT 0, average_price numeric(18,4) NOT NULL DEFAULT 0,
 source text NOT NULL DEFAULT 'DUMMY', reconciliation_status text NOT NULL DEFAULT 'MATCHED', updated_at timestamptz NOT NULL DEFAULT now(),
 PRIMARY KEY(broker,account_id,symbol)
);
CREATE TABLE trade.fills (
 id text PRIMARY KEY, order_id text REFERENCES trade.orders(id), quantity int NOT NULL, price numeric(18,4) NOT NULL, created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE trade.audit (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY, actor text NOT NULL, action text NOT NULL, entity_id text,
 outcome text NOT NULL, details jsonb NOT NULL DEFAULT '{}', created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX orders_owner ON trade.orders(owner_id,created_at DESC);
CREATE INDEX runs_strategy ON trade.runs(strategy_id,started_at DESC);
CREATE INDEX audit_created ON trade.audit(created_at DESC);
REVOKE ALL ON SCHEMA trade FROM PUBLIC;
