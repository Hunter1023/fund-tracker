-- 用户表
CREATE TABLE IF NOT EXISTS "user" (
    id SERIAL PRIMARY KEY,
    email VARCHAR(255) UNIQUE,
    username VARCHAR(100) UNIQUE,
    password_hash VARCHAR(255),
    github_id VARCHAR(100) UNIQUE,
    github_username VARCHAR(100),
    github_avatar VARCHAR(500),
    nickname VARCHAR(100),
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_user_email ON "user"(email);
CREATE INDEX IF NOT EXISTS ix_user_username ON "user"(username);
CREATE INDEX IF NOT EXISTS ix_user_github_id ON "user"(github_id);

-- 基金信息表
CREATE TABLE IF NOT EXISTS fund (
    id SERIAL PRIMARY KEY,
    fund_code VARCHAR(10) UNIQUE NOT NULL,
    fund_name VARCHAR(100) NOT NULL,
    fund_type VARCHAR(50),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_fund_fund_code ON fund(fund_code);

-- 基金实时数据表
CREATE TABLE IF NOT EXISTS fund_realtime_data (
    id SERIAL PRIMARY KEY,
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
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (fund_id) REFERENCES fund(id)
);

CREATE INDEX IF NOT EXISTS ix_fund_realtime_data_fund_id ON fund_realtime_data(fund_id);

-- 基金持仓表
CREATE TABLE IF NOT EXISTS fund_holding (
    id SERIAL PRIMARY KEY,
    fund_id INTEGER NOT NULL,
    user_id INTEGER,
    cost REAL NOT NULL,
    shares REAL NOT NULL,
    avg_cost REAL NOT NULL,
    current_value REAL,
    profit_loss REAL,
    profit_loss_rate REAL,
    platform VARCHAR(50) DEFAULT '其他',
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (fund_id) REFERENCES fund(id),
    FOREIGN KEY (user_id) REFERENCES "user"(id)
);

CREATE INDEX IF NOT EXISTS ix_fund_holding_user_id ON fund_holding(user_id);

-- 交易记录表
CREATE TABLE IF NOT EXISTS transaction (
    id SERIAL PRIMARY KEY,
    fund_id INTEGER NOT NULL,
    user_id INTEGER,
    platform_id INTEGER,
    transaction_type VARCHAR(10) NOT NULL,
    amount REAL NOT NULL,
    shares REAL NOT NULL,
    price REAL NOT NULL,
    transaction_date TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (fund_id) REFERENCES fund(id),
    FOREIGN KEY (user_id) REFERENCES "user"(id),
    FOREIGN KEY (platform_id) REFERENCES platform(id)
);

CREATE INDEX IF NOT EXISTS ix_transaction_user_id ON transaction(user_id);

-- 持仓收益历史记录表
CREATE TABLE IF NOT EXISTS holding_profit_history (
    id SERIAL PRIMARY KEY,
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
    recorded_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (holding_id) REFERENCES fund_holding(id)
);

CREATE INDEX IF NOT EXISTS ix_holding_profit_history_fund_code ON holding_profit_history(fund_code);
CREATE INDEX IF NOT EXISTS ix_holding_profit_history_recorded_at ON holding_profit_history(recorded_at);

-- 自选基金表
CREATE TABLE IF NOT EXISTS watchlist (
    id SERIAL PRIMARY KEY,
    fund_id INTEGER NOT NULL,
    user_id INTEGER,
    tags VARCHAR(255) DEFAULT '',
    added_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (fund_id) REFERENCES fund(id),
    FOREIGN KEY (user_id) REFERENCES "user"(id),
    UNIQUE (fund_id, user_id)
);

CREATE INDEX IF NOT EXISTS ix_watchlist_user_id ON watchlist(user_id);

-- 平台表
CREATE TABLE IF NOT EXISTS platform (
    id SERIAL PRIMARY KEY,
    name VARCHAR(50) NOT NULL,
    user_id INTEGER,
    order_num INTEGER DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES "user"(id),
    UNIQUE (name, user_id)
);

CREATE INDEX IF NOT EXISTS ix_platform_user_id ON platform(user_id);
