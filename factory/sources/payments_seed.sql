-- OrderFlow Pipeline Factory — Payments Seed Data
-- Creates the payments table in PostgreSQL and seeds it with demo data.
-- Run against the orderflow database on postgres.databases.svc.
-- Prerequisites: the orders table must already exist (Phase 1 seed).

CREATE TABLE IF NOT EXISTS payments (
    id SERIAL PRIMARY KEY,
    order_id INTEGER REFERENCES orders(id),
    amount NUMERIC(10,2) NOT NULL,
    method VARCHAR(20) NOT NULL,
    card_last_four VARCHAR(4),
    status VARCHAR(20) DEFAULT 'pending',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

INSERT INTO payments (order_id, amount, method, card_last_four, status)
SELECT
    id,
    total_amount,
    (ARRAY['credit_card', 'debit_card', 'cash', 'wallet'])[floor(random()*4+1)],
    lpad(floor(random()*10000)::text, 4, '0'),
    'completed'
FROM orders
LIMIT 1000;
