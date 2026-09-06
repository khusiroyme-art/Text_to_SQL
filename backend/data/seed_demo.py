"""Creates backend/data/demo.sqlite - a small sales dataset (4 tables, joins).

Run: python backend/data/seed_demo.py
"""

import os
import sqlite3

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "demo.sqlite")

SCHEMA = """
DROP TABLE IF EXISTS order_items;
DROP TABLE IF EXISTS orders;
DROP TABLE IF EXISTS products;
DROP TABLE IF EXISTS customers;

CREATE TABLE customers (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    city TEXT NOT NULL,
    country TEXT NOT NULL,
    signup_date TEXT NOT NULL
);

CREATE TABLE products (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    category TEXT NOT NULL,
    unit_price REAL NOT NULL
);

CREATE TABLE orders (
    id INTEGER PRIMARY KEY,
    customer_id INTEGER NOT NULL REFERENCES customers(id),
    order_date TEXT NOT NULL,
    status TEXT NOT NULL
);

CREATE TABLE order_items (
    id INTEGER PRIMARY KEY,
    order_id INTEGER NOT NULL REFERENCES orders(id),
    product_id INTEGER NOT NULL REFERENCES products(id),
    quantity INTEGER NOT NULL,
    unit_price REAL NOT NULL
);
"""

CUSTOMERS = [
    (1, "Ada Lovelace", "London", "UK", "2023-01-14"),
    (2, "Grace Hopper", "New York", "USA", "2023-02-03"),
    (3, "Alan Turing", "Manchester", "UK", "2023-02-19"),
    (4, "Katherine Johnson", "Hampton", "USA", "2023-03-08"),
    (5, "Rohini Devi", "Bengaluru", "India", "2023-04-21"),
    (6, "Kenji Tanaka", "Osaka", "Japan", "2023-05-30"),
]

PRODUCTS = [
    (1, "Mechanical Keyboard", "Peripherals", 129.00),
    (2, "27in Monitor", "Displays", 349.50),
    (3, "USB-C Dock", "Peripherals", 189.99),
    (4, "Noise Cancelling Headphones", "Audio", 279.00),
    (5, "Webcam 1080p", "Peripherals", 79.95),
    (6, "Standing Desk", "Furniture", 599.00),
]

ORDERS = [
    (1, 1, "2024-01-05", "shipped"),
    (2, 2, "2024-01-17", "shipped"),
    (3, 1, "2024-02-02", "shipped"),
    (4, 3, "2024-02-11", "cancelled"),
    (5, 4, "2024-03-04", "shipped"),
    (6, 5, "2024-03-22", "pending"),
    (7, 6, "2024-04-09", "shipped"),
    (8, 2, "2024-04-27", "shipped"),
    (9, 5, "2024-05-14", "shipped"),
    (10, 4, "2024-06-01", "pending"),
]

ORDER_ITEMS = [
    (1, 1, 1, 1, 129.00),
    (2, 1, 5, 2, 79.95),
    (3, 2, 2, 2, 349.50),
    (4, 3, 4, 1, 279.00),
    (5, 4, 6, 1, 599.00),
    (6, 5, 3, 1, 189.99),
    (7, 5, 1, 1, 129.00),
    (8, 6, 2, 1, 349.50),
    (9, 7, 4, 2, 279.00),
    (10, 8, 6, 1, 599.00),
    (11, 8, 5, 1, 79.95),
    (12, 9, 3, 2, 189.99),
    (13, 10, 1, 3, 129.00),
]


def main() -> None:
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(SCHEMA)
    conn.executemany("INSERT INTO customers VALUES (?,?,?,?,?)", CUSTOMERS)
    conn.executemany("INSERT INTO products VALUES (?,?,?,?)", PRODUCTS)
    conn.executemany("INSERT INTO orders VALUES (?,?,?,?)", ORDERS)
    conn.executemany("INSERT INTO order_items VALUES (?,?,?,?,?)", ORDER_ITEMS)
    conn.commit()
    conn.close()
    print(f"seeded {DB_PATH}")


if __name__ == "__main__":
    main()
