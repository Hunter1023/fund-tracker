# 配置文件

# 数据源API地址
DATA_SOURCES = {
    'fund_valuation': 'http://fundgz.1234567.com.cn/js/',  # 天天基金估值
    'eastmoney': 'http://fundf10.eastmoney.com/',  # 东方财富基金详情
    'tencent_stock': 'http://qt.gtimg.cn/q='  # 腾讯财经股票行情
}

# 数据库配置
import os
# 使用环境变量中的数据库路径，如果没有则使用默认路径
DATABASE_PATH = os.environ.get('DATABASE_PATH', os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "fund_tracker.db"))
DATABASE_URL = f'sqlite:///{DATABASE_PATH}'

# SQLite 连接参数，用于改善并发性能
SQLITE_CONNECT_ARGS = {
    'check_same_thread': False,
    'timeout': 30  # 设置30秒超时，避免快速锁定
}

# 刷新间隔（秒）
REFRESH_INTERVAL = 30
