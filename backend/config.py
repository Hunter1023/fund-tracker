# 配置文件

# 数据源API地址
DATA_SOURCES = {
    'fund_valuation': 'http://fundgz.1234567.com.cn/js/',  # 天天基金估值
    'eastmoney': 'http://fundf10.eastmoney.com/',  # 东方财富基金详情
    'tencent_stock': 'http://qt.gtimg.cn/q='  # 腾讯财经股票行情
}

# 数据库配置
DATABASE_URL = 'sqlite:///fund_tracker.db'

# SQLite 连接参数，用于改善并发性能
SQLITE_CONNECT_ARGS = {
    'check_same_thread': False,
    'timeout': 30  # 设置30秒超时，避免快速锁定
}

# 刷新间隔（秒）
REFRESH_INTERVAL = 30
