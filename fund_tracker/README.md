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
│   └── requirements.txt  # Python依赖
├── frontend/         # 前端应用 (Vue 3)
│   ├── src/
│   │   ├── components/  # Vue组件
│   │   ├── composables/ # 组合式函数
│   │   └── services/    # API服务
│   ├── package.json     # Node依赖
│   └── vite.config.js   # Vite配置文件
├── database_schema.sql   # 数据库表结构SQL
├── database_init_data.sql  # 数据库初始化数据SQL
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

### 环境要求
- Python 3.8+
- Node.js 16+
- npm 或 yarn

### 后端安装

```bash
cd fund_tracker/backend

# 安装依赖
pip install -r requirements.txt

# 启动后端服务
python app.py
```

后端服务将在 `http://localhost:5000` 启动

### 前端安装

```bash
cd fund_tracker/frontend

# 安装依赖
npm install

# 启动开发服务器
npm run dev
```

前端服务将在 `http://localhost:5173` 启动

### 数据库初始化

项目使用 SQLite 数据库，首次运行时会自动创建数据库文件 `fund_tracker.db` 和表结构。

如果需要手动初始化数据库，可以使用以下步骤：

```bash
# 在 backend 目录下
# 方式1：直接运行应用（会自动创建表结构）
python app.py

# 方式2：手动执行数据库迁移（如果需要）
python migrate_db.py
```

**注意**：数据库文件 `fund_tracker.db` 包含个人持仓数据，已在 `.gitignore` 中排除，不会被上传到 GitHub。

### 生产环境部署

```bash
# 构建前端
cd fund_tracker/frontend
npm run build

# 前端构建产物在 dist/ 目录
```

### 完整运行步骤

1. **克隆项目**
   ```bash
   git clone <repository-url>
   cd fund
   ```

2. **安装后端依赖**
   ```bash
   cd fund_tracker/backend
   pip install -r requirements.txt
   ```

3. **安装前端依赖**
   ```bash
   cd ../frontend
   npm install
   ```

4. **启动后端服务**
   ```bash
   # 在 backend 目录
   python app.py
   ```

5. **启动前端服务**
   ```bash
   # 在 frontend 目录
   npm run dev
   ```

6. **访问应用**
   - 前端：http://localhost:5173
   - 后端 API：http://localhost:5000/api

### 重置数据库（可选）

如果需要重置数据库，可以：

1. 删除 `fund_tracker.db` 文件
2. 重新启动后端服务，会自动创建新的数据库文件和表结构
3. 或者使用提供的 SQL 文件初始化：
   ```bash
   # 在项目根目录
   sqlite3 fund_tracker/backend/fund_tracker.db < database_schema.sql
   sqlite3 fund_tracker/backend/fund_tracker.db < database_init_data.sql
   ```

## API 接口

### 基金相关
- `GET /api/fund/search?keyword={keyword}` - 搜索基金
- `GET /api/fund/{fund_code}` - 获取基金详情
- `GET /api/fund/{fund_code}/chart` - 获取基金图表数据
- `GET /api/fund/{fund_code}/history` - 获取基金历史净值

### 自选基金
- `GET /api/watchlist` - 获取自选基金列表
- `POST /api/watchlist` - 添加自选基金
- `DELETE /api/watchlist` - 删除自选基金
- `PUT /api/watchlist/tags` - 更新自选基金标签

### 持仓管理
- `GET /api/holding` - 获取持仓列表
- `POST /api/holding` - 添加持仓
- `PUT /api/holding/{fund_code}` - 更新持仓
- `DELETE /api/holding/{fund_code}` - 删除持仓
- `PUT /api/holding/tags` - 更新持仓标签
- `GET /api/transaction/{fund_code}` - 获取交易记录

### 平台管理
- `GET /api/platform` - 获取平台列表
- `POST /api/platform` - 添加平台
- `PUT /api/platform/{id}` - 更新平台
- `DELETE /api/platform/{id}` - 删除平台

## 数据库结构

### Fund (基金信息表)
- `id` - 主键
- `fund_code` - 基金代码
- `fund_name` - 基金名称
- `fund_type` - 基金类型
- `created_at` - 创建时间

### FundRealtimeData (基金实时数据表)
- `id` - 主键
- `fund_id` - 基金ID
- `net_value_date` - 净值日期
- `unit_net_value` - 单位净值
- `estimate_net_value` - 估算净值
- `estimate_change_rate` - 估算涨跌幅
- `estimate_time` - 估值时间
- `one_month_rate` - 近1月收益率
- `three_month_rate` - 近3月收益率
- `one_year_rate` - 近1年收益率
- `daily_change_rate` - 日涨跌幅
- `fsrq` - 净值日期
- `net_values` - 历史净值数据(JSON)
- `updated_at` - 更新时间

### FundHolding (基金持仓表)
- `id` - 主键
- `fund_id` - 基金ID
- `cost` - 持仓成本
- `shares` - 持仓份额
- `avg_cost` - 平均成本
- `current_value` - 当前价值
- `profit_loss` - 盈亏金额
- `profit_loss_rate` - 盈亏比例
- `platform` - 平台（如：支付宝、理财通等）
- `updated_at` - 更新时间

### Transaction (交易记录表)
- `id` - 主键
- `fund_id` - 基金ID
- `transaction_type` - 交易类型(buy/sell)
- `amount` - 交易金额
- `shares` - 交易份额
- `price` - 交易价格
- `transaction_date` - 交易时间

### Watchlist (自选基金表)
- `id` - 主键
- `fund_id` - 基金ID
- `tags` - 标签(逗号分隔)
- `added_at` - 添加时间

### Platform (平台表)
- `id` - 主键
- `name` - 平台名称（如：支付宝、理财通）
- `order` - 排序顺序
- `created_at` - 创建时间

## 配置说明

后端配置文件 `config.py`:

```python
# 数据源API地址
DATA_SOURCES = {
    'fund_valuation': 'http://fundgz.1234567.com.cn/js/',
    'eastmoney': 'http://fundf10.eastmoney.com/',
    'tencent_stock': 'http://qt.gtimg.cn/q='
}

# 数据库配置
DATABASE_URL = 'sqlite:///fund_tracker.db'

# 刷新间隔（秒）
REFRESH_INTERVAL = 30
```

## 注意事项

1. **数据缓存**: 基金数据会缓存10分钟，避免频繁请求API
2. **交易日判断**: 持仓收益更新仅在交易日19:00-23:00期间执行
3. **数据库**: 默认使用SQLite，数据库文件为 `fund_tracker.db`
4. **跨域**: 后端已配置CORS，支持前端跨域请求

## 许可证

MIT
