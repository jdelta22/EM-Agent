CREATE EXTENSION IF NOT EXISTS unaccent;

CREATE TABLE IF NOT EXISTS categories (
    category_id integer PRIMARY KEY,
    name        text NOT NULL,
    description text
);

CREATE TABLE IF NOT EXISTS products (
    product_id     integer PRIMARY KEY,
    name           text NOT NULL,
    category_id    integer NOT NULL REFERENCES categories (category_id),
    description    text,
    price_brl      numeric(10, 2) NOT NULL,
    stock_quantity integer NOT NULL DEFAULT 0,
    status         text NOT NULL,  -- active | discontinued | coming_soon
    specs          jsonb,
    created_at     date
);

CREATE TABLE IF NOT EXISTS promotions (
    promotion_id     integer PRIMARY KEY,
    product_id       integer NOT NULL REFERENCES products (product_id),
    discount_percent numeric(5, 2) NOT NULL,
    description      text,
    is_active        boolean NOT NULL
);

CREATE TABLE IF NOT EXISTS customers (
    customer_id integer PRIMARY KEY,
    name        text NOT NULL,
    phone       text,
    email       text,
    city        text
);

CREATE TABLE IF NOT EXISTS orders (
    order_id           integer PRIMARY KEY,
    customer_id        integer NOT NULL REFERENCES customers (customer_id),
    order_date         date NOT NULL,
    status             text NOT NULL,  -- pending | confirmed | shipped | delivered | cancelled
    total_brl          numeric(10, 2) NOT NULL,
    payment_method     text,
    tracking_code      text,
    estimated_delivery date,
    notes              text
);

CREATE TABLE IF NOT EXISTS order_items (
    id         serial PRIMARY KEY,
    order_id   integer NOT NULL REFERENCES orders (order_id),
    product_id integer NOT NULL REFERENCES products (product_id),
    quantity   integer NOT NULL
);

-- Store policy manual, split by section. `search` is a pre-built tsvector (accent-insensitive).
CREATE TABLE IF NOT EXISTS policy_chunks (
    id      serial PRIMARY KEY,
    section text NOT NULL,
    title   text NOT NULL,
    content text NOT NULL,
    search  tsvector NOT NULL
);

CREATE INDEX IF NOT EXISTS policy_chunks_search_idx ON policy_chunks USING gin (search);
CREATE INDEX IF NOT EXISTS orders_customer_idx ON orders (customer_id);
CREATE INDEX IF NOT EXISTS order_items_order_idx ON order_items (order_id);
CREATE INDEX IF NOT EXISTS promotions_product_idx ON promotions (product_id);
