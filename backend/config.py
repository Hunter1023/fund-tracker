# 配置文件

import os
from pathlib import Path
from dotenv import load_dotenv

_project_root = Path(__file__).resolve().parent.parent
load_dotenv(_project_root / '.env')

# 数据源API地址
DATA_SOURCES = {
    'fund_valuation': 'http://fundgz.1234567.com.cn/js/',
    'eastmoney': 'http://fundf10.eastmoney.com/',
    'tencent_stock': 'http://qt.gtimg.cn/q='
}

# 数据库配置

DB_USER = os.environ.get('DB_USER', 'postgres')
DB_PASSWORD = os.environ.get('DB_PASSWORD', 'postgres')
DB_HOST = os.environ.get('DB_HOST', 'localhost')
DB_PORT = os.environ.get('DB_PORT', '5432')
DB_NAME = os.environ.get('DB_NAME', 'fund_tracker')
DATABASE_URL = f'postgresql+psycopg2://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}'
CONNECT_ARGS = {'options': '-c timezone=UTC'}

# JWT配置
_jwt_env = os.environ.get('JWT_SECRET_KEY')
if _jwt_env:
    JWT_SECRET_KEY = _jwt_env
else:
    import secrets
    JWT_SECRET_KEY = secrets.token_urlsafe(32)
    print(f"[警告] JWT_SECRET_KEY 未设置，已自动生成随机密钥。重启后Token将失效，生产环境请设置环境变量！")
JWT_ACCESS_TOKEN_EXPIRES = int(os.environ.get('JWT_ACCESS_TOKEN_EXPIRES', 86400))

# GitHub OAuth配置
GITHUB_CLIENT_ID = os.environ.get('GITHUB_CLIENT_ID', '')
GITHUB_CLIENT_SECRET = os.environ.get('GITHUB_CLIENT_SECRET', '')

# SMTP邮件配置（用于发送邮箱验证码）
SMTP_HOST = os.environ.get('SMTP_HOST', '')
SMTP_PORT = int(os.environ.get('SMTP_PORT', '587'))
SMTP_USER = os.environ.get('SMTP_USER', '')
SMTP_PASSWORD = os.environ.get('SMTP_PASSWORD', '')
SMTP_FROM = os.environ.get('SMTP_FROM', '')

# 默认公开自选基金代码（未登录用户可见）
DEFAULT_PUBLIC_FUNDS = os.environ.get('DEFAULT_PUBLIC_FUNDS', '000001,000011,000051,110011,161725').split(',')

# 刷新间隔（秒）
REFRESH_INTERVAL = 30
