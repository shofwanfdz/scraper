-- ============================================
-- Scraping Tools - Database Setup Script
-- Run this in phpMyAdmin or MySQL CLI
-- ============================================

-- Create database
CREATE DATABASE IF NOT EXISTS scraping_db
CHARACTER SET utf8mb4
COLLATE utf8mb4_unicode_ci;

USE scraping_db;

-- Grant privileges (if needed)
-- GRANT ALL PRIVILEGES ON scraping_db.* TO 'root'@'localhost';
-- FLUSH PRIVILEGES;

SELECT 'Database scraping_db created successfully!' AS status;
