# 基金追踪系统

一个实时基金估值和持仓管理工具，支持自选基金管理、持仓追踪、实时估值显示等功能。

## 项目架构

```
fund_tracker/
├── backend/          # 后端服务 (Flask)
│   ├── app.py        # 主应用文件，包含API路由和定时任务
│   ├── models.py     # 数据库模型定义
│   ├── data_fetcher.py  # 数据获取模块
│   ├── config.py     # 配置文件
│   ├── Dockerfile    # 后端容器配置
│   └── requirements.txt  # Python依赖
├── frontend/         # 前端应用 (Vue 3)
│   ├── src/
│   │   ├── components/  # Vue组件
│   │   ├── composables/ # 组合式函数
│   │   └── services/    # API服务
│   ├── package.json     # Node依赖
│   ├── vite.config.js   # Vite配置文件
│   ├── Dockerfile        # 前端容器配置
│   └── nginx.conf        # Nginx配置
├── database_schema.sql   # 数据库表结构SQL
├── database_init_data.sql  # 数据库初始化数据SQL
├── docker-compose.yml   # Docker Compose配置
├── .env                # 环境变量配置（本地配置，不提交到Git）
├── .gitignore        # Git忽略文件配置
└── README.md         # 项目说明文档
```

## 技术栈

### 后端
- **Flask** - Web框架
- **SQLAlchemy** - ORM框架
- **SQLite** - 数据库
- **APScheduler** - 定时任务调度
- **Flask-CORS** - 跨域支持
- **requests** - HTTP请求
- **BeautifulSoup4** - HTML解析

### 前端
- **Vue 3** - 前端框架
- **Vite** - 构建工具
- **Axios** - HTTP客户端
- **Bootstrap 5** - UI框架
- **Bootstrap Icons** - 图标库
- **Chart.js** - 图表库

## 主要功能

### 1. 基金搜索
- 支持按基金代码或名称搜索
- 实时显示搜索结果
- 显示基金是否已在自选或持仓中

### 2. 自选基金管理
- 添加基金到自选列表
- 支持标签分类（如：AI、新能源等）
- 实时显示基金估值和涨跌幅
- 显示近1月、近3月、近1年收益率
- 从自选中移除基金
- 修改基金标签

### 3. 持仓管理
- 添加持仓基金（输入成本和份额）
- 自动计算持仓盈亏
- 实时更新持仓价值
- 显示盈亏金额和收益率
- 删除持仓
- 查看交易记录

### 4. 基金详情
- 查看基金历史净值走势图
- 显示近1月、近3月、近1年收益率
- 显示昨日涨跌幅
- 显示最新净值和估算净值

### 5. 定时任务
- 每10分钟自动更新所有基金数据
- 交易日19:00-23:00期间，每10分钟检查并更新持仓收益

## 数据来源

- **天天基金** - 基金实时估值数据
- **东方财富** - 基金历史净值和涨跌幅数据
- **腾讯财经** - 股票行情数据

## 快速开始

### 部署


使用 Docker Compose 可以快速部署整个应用，包括后端、前端和 Cloudflare Tunnel。

**1. 环境准备**
- 安装 Docker Desktop
- 安装 Docker Compose

**2. 配置环境变量**

创建 `.env` 文件（项目根目录）：

```env
# Cloudflare Tunnel 配置
# 获取方式：访问 https://dash.cloudflare.com/ -> Zero Trust -> Networks -> Tunnels
TUNNEL_TOKEN=your_tunnel_token_here

# 数据库配置（可选，默认使用SQLite）
# DATABASE_PATH=/app/data/fund_tracker.db

# 后端配置（可选）
# FLASK_ENV=production
# FLASK_DEBUG=0

# API配置（可选）
# API_HOST=0.0.0.0
# API_PORT=5000
```

**3. 启动服务**

```bash
# 在项目根目录执行
docker-compose up -d --build
```

**4. 查看服务状态**

```bash
# 查看容器状态
docker-compose ps

# 查看日志
docker-compose logs -f

# 查看特定服务日志
docker-compose logs -f backend
docker-compose logs -f frontend
docker-compose logs -f cloudflared
```

**5. 停止服务**

```bash
# 停止所有服务
docker-compose down

# 停止并删除数据卷（谨慎使用，会删除数据库数据）
docker-compose down -v
```

**6. 重启服务**

```bash
docker-compose restart
```

**7. 访问应用**

- 本地访问：http://localhost
- 公网访问：通过 Cloudflare Tunnel 配置的域名访问

**服务说明：**

- **backend**：Flask 后端服务，运行在容器内 5000 端口
- **frontend**：Nginx 前端服务，映射到主机 80 端口
- **cloudflared**：Cloudflare Tunnel 服务，提供公网访问
- **data**：数据持久化卷，存储 SQLite 数据库

**数据持久化：**

数据库文件存储在 `./data` 目录下，容器重启不会丢失数据。

## 配置说明

### Docker 环境变量 `.env`:

```env
# Cloudflare Tunnel 配置（必需）
TUNNEL_TOKEN=your_tunnel_token_here

# 数据库路径（可选，默认值：/app/data/fund_tracker.db）
DATABASE_PATH=/app/data/fund_tracker.db

# Flask 环境（可选，默认值：production）
FLASK_ENV=production

# Flask 调试模式（可选，默认值：0）
FLASK_DEBUG=0

# API 监听地址（可选，默认值：0.0.0.0）
API_HOST=0.0.0.0

# API 监听端口（可选，默认值：5000）
API_PORT=5000
```

### Cloudflare Tunnel 配置

Cloudflare Tunnel 用于提供公网访问，无需开放端口。

**获取 TUNNEL_TOKEN：**

1. 登录 [Cloudflare Dashboard](https://dash.cloudflare.com/)
2. 进入 **Zero Trust** → **Networks** → **Tunnels**
3. 点击 **Create a tunnel**
4. 选择 **Docker** 或 **Cloudflared** 安装方式
5. 复制生成的 **Tunnel Token**
6. 将 Token 填入 `.env` 文件的 `TUNNEL_TOKEN` 变量

**配置域名：**

1. 在 Cloudflare Dashboard 中选择你的域名
2. 进入 **Zero Trust** → **Access** → **Applications**
3. 点击 **Add an application**
4. 选择 **Self-hosted**
5. 配置：
   - **Subdomain**: 子域名（如：fundtracker）
   - **Domain**: 你的域名
   - **Type**: HTTP
   - **URL**: http://localhost:80
6. 保存配置

**访问方式：**

配置完成后，可以通过 `https://fundtracker.yourdomain.com` 访问应用。

## 注意事项

1. **数据缓存**: 基金数据会缓存10分钟，避免频繁请求API
2. **交易日判断**: 持仓收益更新仅在交易日19:00-23:00期间执行
3. **数据库**: 默认使用SQLite，数据库文件为 `fund_tracker.db`
4. **跨域**: 后端已配置CORS，支持前端跨域请求
5. **环境变量**: `.env` 文件包含敏感信息，已在 `.gitignore` 中排除，不会被提交到 Git
6. **数据持久化**: Docker Compose 部署时，数据库数据存储在 `./data` 目录，容器重启不会丢失数据
7. **端口占用**: 确保 80 端口未被占用，否则需要修改 `docker-compose.yml` 中的端口映射
8. **Cloudflare Tunnel**: Tunnel Token 是敏感信息，请妥善保管，不要泄露

## 许可证

MIT
