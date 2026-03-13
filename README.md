# 基金追踪系统

一个实时基金估值和持仓管理工具，支持自选基金管理、持仓追踪、实时估值显示等功能。

预览地址：https://fundtracker.cc.cd/



![image-20260313204925393](https://files.seeusercontent.com/2026/03/13/bLn3/image-20260313204925393.png)



## 数据来源

- **天天基金** - 基金实时估值数据
- **东方财富** - 基金历史净值和涨跌幅数据
- **腾讯财经** - 股票行情数据

## 快速部署


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
