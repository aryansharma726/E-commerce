-- Active: 1746695805491@@127.0.0.1@3306
-- You can run these queries using a simple Python script or an SQLite client (like DB Browser for SQLite)

-- Enable foreign key constraints (run this after connecting)
PRAGMA foreign_keys = ON;

-- Create the orders table (SQLite syntax)
CREATE TABLE IF NOT EXISTS orders (
    order_id VARCHAR(255) PRIMARY KEY, -- Unique ID for the order
    user_id VARCHAR(255),           -- ID of the user who placed the order
    status VARCHAR(50),             -- Current status (e.g., 'Processing', 'Shipped')
    created_at DATETIME,            -- Timestamp when the order was created (SQLite DATETIME)
    details TEXT                    -- Additional details
);

-- Create the order_items table (SQLite syntax)
CREATE TABLE IF NOT EXISTS order_items (
    item_id INTEGER PRIMARY KEY AUTOINCREMENT, -- Auto-incrementing integer primary key in SQLite
    order_id VARCHAR(255),                  -- The ID of the order this item belongs to
    product_id VARCHAR(255),                -- The ID of the product ordered
    quantity INTEGER,                       -- The quantity (SQLite INTEGER)
    -- Define the foreign key constraint
    FOREIGN KEY (order_id) REFERENCES orders(order_id) ON DELETE CASCADE
);
ALTER TABLE order_items ADD COLUMN price REAL;

ALTER TABLE orders ADD COLUMN total_price REAL DEFAULT 0.0;