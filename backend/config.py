# 配置文件

# 数据源API地址
DATA_SOURCES = {
    'fund_valuation': 'http://fundgz.1234567.com.cn/js/',  # 天天基金估值
    'eastmoney': 'http://fundf10.eastmoney.com/',  # 东方财富基金详情
    'tencent_stock': 'http://qt.gtimg.cn/q='  # 腾讯财经股票行情
}

# 数据库配置
import os

# PostgreSQL配置
DB_USER = os.environ.get('DB_USER', 'postgres')
DB_PASSWORD = os.environ.get('DB_PASSWORD', 'postgres')
DB_HOST = os.environ.get('DB_HOST', 'localhost')
DB_PORT = os.environ.get('DB_PORT', '5432')
DB_NAME = os.environ.get('DB_NAME', 'fund_tracker')
DATABASE_URL = f'postgresql+psycopg2://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}'
# PostgreSQL连接参数，设置时区为UTC
CONNECT_ARGS = {'options': '-c timezone=UTC'}

# 刷新间隔（秒）
REFRESH_INTERVAL = 30
