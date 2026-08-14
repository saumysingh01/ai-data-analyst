-- ============================================================
-- E-Commerce BI Database Schema
-- ============================================================

-- Drop tables if they exist (for clean initialization)
DROP TABLE IF EXISTS orders;
DROP TABLE IF EXISTS products;
DROP TABLE IF EXISTS users;

-- ============================================================
-- Users Table
-- ============================================================
CREATE TABLE users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    email TEXT UNIQUE NOT NULL,
    signup_date DATE NOT NULL
);

-- ============================================================
-- Products Table
-- ============================================================
CREATE TABLE products (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    category TEXT NOT NULL,
    price DECIMAL(10, 2) NOT NULL,
    stock INTEGER NOT NULL DEFAULT 0
);

-- ============================================================
-- Orders Table
-- ============================================================
CREATE TABLE orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    product_id INTEGER NOT NULL,
    order_date DATE NOT NULL,
    quantity INTEGER NOT NULL DEFAULT 1,
    total_amount DECIMAL(10, 2) NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE
);

-- ============================================================
-- Mock Data: Users
-- ============================================================
INSERT INTO users (name, email, signup_date) VALUES
('Alice Johnson', 'alice.johnson@email.com', '2023-01-15'),
('Bob Smith', 'bob.smith@email.com', '2023-02-20'),
('Charlie Brown', 'charlie.brown@email.com', '2023-03-10'),
('Diana Prince', 'diana.prince@email.com', '2023-04-05'),
('Evan Wright', 'evan.wright@email.com', '2023-05-12'),
('Fiona Green', 'fiona.green@email.com', '2023-06-18'),
('George Miller', 'george.miller@email.com', '2023-07-22'),
('Hannah Davis', 'hannah.davis@email.com', '2023-08-30'),
('Ian Clark', 'ian.clark@email.com', '2023-09-14'),
('Julia Roberts', 'julia.roberts@email.com', '2023-10-01');

-- ============================================================
-- Mock Data: Products
-- ============================================================
INSERT INTO products (name, category, price, stock) VALUES
('Wireless Bluetooth Headphones', 'Electronics', 79.99, 150),
('Organic Green Tea - 50 Bags', 'Groceries', 12.50, 300),
('Stainless Steel Water Bottle', 'Home & Kitchen', 24.99, 200),
('Running Shoes - Mens Size 10', 'Sports & Outdoors', 89.99, 75),
('Yoga Mat - Premium Non-Slip', 'Sports & Outdoors', 35.00, 120),
('Smart LED Desk Lamp', 'Electronics', 45.99, 80),
('Gourmet Dark Chocolate Bar', 'Groceries', 5.99, 500),
('Ceramic Coffee Mug Set (4pcs)', 'Home & Kitchen', 29.99, 60),
('Mechanical Keyboard RGB', 'Electronics', 129.99, 45),
('Protein Powder - Vanilla 2lb', 'Sports & Outdoors', 49.99, 90);

-- ============================================================
-- Mock Data: Orders
-- ============================================================
INSERT INTO orders (user_id, product_id, order_date, quantity, total_amount) VALUES
(1, 1, '2023-06-10', 1, 79.99),
(1, 3, '2023-06-15', 2, 49.98),
(2, 2, '2023-07-01', 3, 37.50),
(2, 5, '2023-07-05', 1, 35.00),
(3, 4, '2023-07-12', 1, 89.99),
(3, 8, '2023-07-20', 2, 59.98),
(4, 6, '2023-08-01', 1, 45.99),
(4, 9, '2023-08-10', 1, 129.99),
(5, 1, '2023-08-15', 2, 159.98),
(5, 7, '2023-08-18', 5, 29.95),
(6, 10, '2023-09-01', 1, 49.99),
(6, 3, '2023-09-05', 3, 74.97),
(7, 2, '2023-09-10', 2, 25.00),
(7, 5, '2023-09-12', 1, 35.00),
(8, 4, '2023-09-20', 1, 89.99),
(8, 6, '2023-09-25', 2, 91.98),
(9, 9, '2023-10-01', 1, 129.99),
(9, 1, '2023-10-05', 1, 79.99),
(10, 8, '2023-10-10', 1, 29.99),
(10, 7, '2023-10-12', 10, 59.90),
(1, 4, '2023-11-01', 1, 89.99),
(2, 10, '2023-11-05', 2, 99.98),
(3, 6, '2023-11-10', 1, 45.99),
(4, 1, '2023-11-15', 3, 239.97),
(5, 3, '2023-11-20', 1, 24.99),
(6, 2, '2023-12-01', 4, 50.00),
(7, 9, '2023-12-05', 1, 129.99),
(8, 5, '2023-12-10', 2, 70.00),
(9, 8, '2023-12-15', 1, 29.99),
(10, 4, '2023-12-20', 1, 89.99);