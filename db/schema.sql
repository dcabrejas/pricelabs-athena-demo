-- Synthetic short-term-rental revenue data for the PriceLabs demo.
-- One row per listing per night: enough volume (~700k rows for the
-- largest customer) that pulling it raw into a model context is a bad idea.

DROP TABLE IF EXISTS nightly_rates;
DROP TABLE IF EXISTS market_events;
DROP TABLE IF EXISTS listings;
DROP TABLE IF EXISTS customers;

CREATE TABLE customers (
    id          serial PRIMARY KEY,
    name        text NOT NULL UNIQUE,
    plan        text NOT NULL
);

CREATE TABLE listings (
    id           text PRIMARY KEY,            -- e.g. CS-00042
    customer_id  int  NOT NULL REFERENCES customers(id),
    market       text NOT NULL,               -- e.g. 'Myrtle Beach, SC'
    bedrooms     int  NOT NULL,
    base_price   numeric(8,2) NOT NULL,       -- current nightly base price
    min_price    numeric(8,2) NOT NULL
);

CREATE TABLE nightly_rates (
    listing_id   text NOT NULL REFERENCES listings(id),
    night        date NOT NULL,
    price        numeric(8,2) NOT NULL,       -- price we listed at
    comp_price   numeric(8,2) NOT NULL,       -- median price of comparable listings
    booked       boolean NOT NULL,
    comp_occupancy numeric(4,3) NOT NULL,     -- share of comp set booked that night
    PRIMARY KEY (listing_id, night)
);
CREATE INDEX nightly_rates_night ON nightly_rates (night);

CREATE TABLE market_events (
    market       text NOT NULL,
    starts       date NOT NULL,
    ends         date NOT NULL,
    name         text NOT NULL,
    demand_lift  numeric(4,2) NOT NULL        -- expected demand multiplier
);

-- Read-only role the MCP server connects as.
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'agent_reader') THEN
    CREATE ROLE agent_reader LOGIN;
  END IF;
END $$;
GRANT USAGE ON SCHEMA public TO agent_reader;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO agent_reader;
ALTER ROLE agent_reader SET statement_timeout = '15s';
ALTER ROLE agent_reader SET default_transaction_read_only = on;
