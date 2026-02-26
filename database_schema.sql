-- 基金信息表
CREATE TABLE IF NOT EXISTS fund (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fund_code VARCHAR(10) UNIQUE NOT NULL,
    fund_name VARCHAR(100) NOT NULL,
    fund_type VARCHAR(50),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_fund_fund_code ON fund(fund_code);

-- 基金实时数据表
CREATE TABLE IF NOT EXISTS fund_realtime_data (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fund_id INTEGER NOT NULL UNIQUE,
    net_value_date VARCHAR(20),
    unit_net_value REAL,
    estimate_net_value REAL,
    estimate_change_rate REAL,
    estimate_time VARCHAR(50),
    one_month_rate REAL DEFAULT 0,
    three_month_rate REAL DEFAULT 0,
    one_year_rate REAL DEFAULT 0,
    daily_change_rate REAL DEFAULT 0,
    fsrq VARCHAR(20),
    net_values TEXT,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (fund_id) REFERENCES fund(id)
);

CREATE INDEX IF NOT EXISTS ix_fund_realtime_data_fund_id ON fund_realtime_data(fund_id);

-- 基金持仓表
CREATE TABLE IF NOT EXISTS fund_holding (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fund_id INTEGER NOT NULL,
    cost REAL NOT NULL,
    shares REAL NOT NULL,
    avg_cost REAL NOT NULL,
    current_value REAL,
    profit_loss REAL,
    profit_loss_rate REAL,
    platform VARCHAR(50) DEFAULT '其他',
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (fund_id) REFERENCES fund(id)
);

-- 交易记录表
CREATE TABLE IF NOT EXISTS transaction (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fund_id INTEGER NOT NULL,
    transaction_type VARCHAR(10) NOT NULL,
    amount REAL NOT NULL,
    shares REAL NOT NULL,
    price REAL NOT NULL,
    transaction_date DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (fund_id) REFERENCES fund(id)
);

-- 持仓收益历史记录表
CREATE TABLE IF NOT EXISTS holding_profit_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    holding_id INTEGER NOT NULL,
    fund_code VARCHAR(10) NOT NULL,
    cost REAL NOT NULL,
    shares REAL NOT NULL,
    avg_cost REAL NOT NULL,
    current_value REAL NOT NULL,
    profit_loss REAL NOT NULL,
    profit_loss_rate REAL NOT NULL,
    unit_net_value REAL NOT NULL,
    fsrq VARCHAR(20) NOT NULL,
    daily_change_rate REAL NOT NULL,
    recorded_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (holding_id) REFERENCES fund_holding(id)
);

CREATE INDEX IF NOT EXISTS ix_holding_profit_history_fund_code ON holding_profit_history(fund_code);
CREATE INDEX IF NOT EXISTS ix_holding_profit_history_recorded_at ON holding_profit_history(recorded_at);

-- 自选基金表
CREATE TABLE IF NOT EXISTS watchlist (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fund_id INTEGER NOT NULL UNIQUE,
    tags VARCHAR(255) DEFAULT '',
    added_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (fund_id) REFERENCES fund(id)
);

-- 平台表
CREATE TABLE IF NOT EXISTS platform (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name VARCHAR(50) UNIQUE NOT NULL,
    order_num INTEGER DEFAULT 0,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
