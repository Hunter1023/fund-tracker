from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from flask_jwt_extended import JWTManager, jwt_required, get_jwt_identity
from data_fetcher import DataFetcher
from models import Fund, FundHolding, Transaction, Watchlist, FundRealtimeData, HoldingProfitHistory, Platform, User, create_tables, get_db
from auth import register_auth_routes, register_user_profile_routes, get_current_user_id
from sqlalchemy.orm import Session
from sqlalchemy import func
import decimal
import time
import json
import logging
import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

CST = ZoneInfo("Asia/Shanghai")

def now_cst():
    return datetime.now(CST)

def now_cst_naive():
    return datetime.now(CST).replace(tzinfo=None)
from apscheduler.schedulers.background import BackgroundScheduler
import threading
from sqlalchemy.exc import OperationalError, IntegrityError
import random
from config import DATABASE_URL, JWT_SECRET_KEY, JWT_ACCESS_TOKEN_EXPIRES, JWT_REFRESH_TOKEN_EXPIRES, DEFAULT_PUBLIC_FUNDS
import concurrent.futures
import traceback

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URL
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['DEBUG'] = True
app.config['SQLALCHEMY_POOL_SIZE'] = 10
app.config['SQLALCHEMY_MAX_OVERFLOW'] = 20
app.config['SQLALCHEMY_POOL_TIMEOUT'] = 30
app.config['SQLALCHEMY_POOL_RECYCLE'] = 1800
app.config['JWT_SECRET_KEY'] = JWT_SECRET_KEY
app.config['JWT_ACCESS_TOKEN_EXPIRES'] = JWT_ACCESS_TOKEN_EXPIRES
app.config['JWT_REFRESH_TOKEN_EXPIRES'] = JWT_REFRESH_TOKEN_EXPIRES
db = SQLAlchemy(app)
CORS(app, supports_credentials=True)
jwt = JWTManager(app)

# 自定义 JWT 错误处理器
@jwt.expired_token_loader
def expired_token_callback(jwt_header, jwt_payload):
    logger.error(f"JWT token 过期: {jwt_header}")
    return jsonify({'error': 'Token 已过期，请重新登录'}), 401

@jwt.invalid_token_loader
def invalid_token_callback(error):
    logger.error(f"JWT token 无效: {error}")
    return jsonify({'error': 'Token 无效'}), 401

@jwt.unauthorized_loader
def unauthorized_callback(error):
    logger.error(f"未授权访问: {error}")
    return jsonify({'error': '请先登录'}), 401

@jwt.revoked_token_loader
def revoked_token_callback(jwt_header, jwt_payload):
    logger.error(f"JWT token 已被撤销")
    return jsonify({'error': 'Token 已被撤销'}), 401

register_auth_routes(app)
register_user_profile_routes(app)

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('holding_profit.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# 数据库操作重试装饰器
def retry_db_operation(max_retries=3, base_delay=0.1):
    """
    数据库操作重试装饰器，用于处理数据库锁定和死锁问题
    """
    def decorator(func):
        def wrapper(*args, **kwargs):
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except OperationalError as e:
                    error_msg = str(e)
                    if ('database is locked' in error_msg or 'deadlock detected' in error_msg) and attempt < max_retries - 1:
                        delay = base_delay * (2 ** attempt) + random.uniform(0, 0.1)
                        logger.warning(f"数据库锁定或死锁，第{attempt + 1}次重试，等待{delay:.2f}秒...")
                        time.sleep(delay)
                    else:
                        logger.error(f"数据库操作失败: {e}")
                        raise
        return wrapper
    return decorator

# 初始化默认平台
def init_default_platform():
    db = next(get_db())
    try:
        # 清理错误的备用平台数据（如"默认_2"、"平台_2"等）
        bad_platforms = db.query(Platform).filter(
            Platform.name.like('默认_%')
        ).all()
        bad_platforms += db.query(Platform).filter(
            Platform.name.like('平台_%')
        ).all()
        for bp in bad_platforms:
            # 将关联的持仓和交易记录迁移到"默认"平台
            default_platform = db.query(Platform).filter(
                Platform.name == '默认',
                Platform.user_id == bp.user_id
            ).first()
            if default_platform:
                db.query(FundHolding).filter(
                    FundHolding.platform == bp.name,
                    FundHolding.user_id == bp.user_id
                ).update({'platform': '默认'})
                db.query(Transaction).filter(
                    Transaction.platform_id == bp.id
                ).update({'platform_id': default_platform.id})
            db.delete(bp)
        if bad_platforms:
            db.commit()

        # 查询所有用户
        users = db.query(User).all()
        for user in users:
            try:
                user_platforms = db.query(Platform).filter(Platform.user_id == user.id).all()

                if not user_platforms:
                    default_platform = Platform(
                        name='默认',
                        user_id=user.id,
                        order_num=0
                    )
                    db.add(default_platform)
                    db.commit()
            except Exception as e:
                db.rollback()
    except Exception as e:
        pass
    finally:
        db.close()

def init_default_user():
    db = next(get_db())
    try:
        admin_user = db.query(User).filter(User.email == 'hspecial@163.com').first()
        if not admin_user:
            admin_user = User(
                email='hspecial@163.com',
                username='hspecial',
                nickname='hspecial',
                is_active=True,
            )
            db.add(admin_user)
            db.commit()
            db.refresh(admin_user)
            print(f"已创建默认管理员用户: {admin_user.email} (ID: {admin_user.id})")
        else:
            print(f"默认管理员用户已存在: {admin_user.email} (ID: {admin_user.id})")

        orphan_watchlist = db.query(Watchlist).filter(Watchlist.user_id == None).all()
        orphan_holdings = db.query(FundHolding).filter(FundHolding.user_id == None).all()
        orphan_transactions = db.query(Transaction).filter(Transaction.user_id == None).all()
        orphan_platforms = db.query(Platform).filter(Platform.user_id == None).all()

        migrated = 0
        for item in orphan_watchlist:
            item.user_id = admin_user.id
            migrated += 1
        for item in orphan_holdings:
            item.user_id = admin_user.id
            migrated += 1
        for item in orphan_transactions:
            item.user_id = admin_user.id
            migrated += 1
        for item in orphan_platforms:
            item.user_id = admin_user.id
            migrated += 1

        if migrated > 0:
            db.commit()
            print(f"已迁移 {migrated} 条无主数据到管理员用户")
        else:
            print("无需迁移数据")
    except Exception as e:
        db.rollback()
        print(f"初始化默认用户时出错: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

# 尝试创建数据库表
try:
    create_tables()
    print("数据库表创建成功")
except Exception as e:
    print(f"数据库表创建失败: {e}")

# 尝试初始化默认平台
try:
    init_default_platform()
except Exception as e:
    print(f"初始化默认平台失败: {e}")

try:
    init_default_user()
except Exception as e:
    print(f"初始化默认用户失败: {e}")

# 创建定时任务调度器
scheduler = BackgroundScheduler()
scheduler.start()

# 定时任务：更新所有基金数据
@retry_db_operation()
def update_all_funds_data():
    """
    定时任务：更新所有自选基金和持仓基金的实时数据
    """
    logger.info(f"[{datetime.now()}] 开始更新基金数据...")
    db = next(get_db())
    try:
        # 获取所有需要更新的基金（自选基金 + 持仓基金 + 公开基金）
        watchlist_funds = db.query(Watchlist).all()
        holding_funds = db.query(FundHolding).all()

        fund_codes = set()
        for item in watchlist_funds:
            if item.fund:
                fund_codes.add(item.fund.fund_code)
        for holding in holding_funds:
            if holding.fund:
                fund_codes.add(holding.fund.fund_code)

        # 添加公开基金到更新列表
        if DEFAULT_PUBLIC_FUNDS:
            fund_codes.update(DEFAULT_PUBLIC_FUNDS)

        logger.info(f"需要更新 {len(fund_codes)} 个基金的数据")

        # 分批处理基金数据，每批5个
        fund_codes_list = list(fund_codes)
        batch_size = 5
        for i in range(0, len(fund_codes_list), batch_size):
            batch_codes = fund_codes_list[i:i+batch_size]
            logger.info(f"处理第 {i//batch_size + 1} 批基金数据，共 {len(batch_codes)} 个基金")

            # 使用线程池并发更新
            with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
                # 为每个基金代码创建一个任务
                future_to_fund = {executor.submit(get_fund_realtime_data, db, fund_code, force_refresh=True, skip_db_write=False): fund_code for fund_code in batch_codes}

                # 处理完成的任务
                for future in concurrent.futures.as_completed(future_to_fund, timeout=30):
                    fund_code = future_to_fund[future]
                    try:
                        future.result()
                        logger.info(f"成功更新基金 {fund_code} 的数据")
                    except Exception as e:
                        logger.error(f"更新基金 {fund_code} 数据失败: {e}")

        logger.info(f"[{datetime.now()}] 基金数据更新完成")
    except Exception as e:
        logger.error(f"定时任务执行失败: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

# 添加定时任务：每10分钟更新一次
scheduler.add_job(update_all_funds_data, 'interval', minutes=10, id='update_funds_data')

# 定时任务：预加载所有基金的历史净值数据
@retry_db_operation()
def preload_all_funds_history():
    """
    定时任务：预加载所有自选基金和持仓基金的历史净值数据到数据库
    每天执行一次，确保历史净值数据已缓存
    返回预加载失败的基金代码列表
    """
    print(f"[{datetime.now()}] 开始预加载基金历史净值数据...")
    db = next(get_db())
    failed_codes = []
    try:
        # 获取所有需要预加载的基金（自选基金 + 持仓基金）
        watchlist_funds = db.query(Watchlist).all()
        holding_funds = db.query(FundHolding).all()

        fund_codes = set()
        for item in watchlist_funds:
            if item.fund:
                fund_codes.add(item.fund.fund_code)
        for holding in holding_funds:
            if holding.fund:
                fund_codes.add(holding.fund.fund_code)

        print(f"需要预加载 {len(fund_codes)} 个基金的历史净值数据")

        # 预加载每个基金的历史净值数据
        for fund_code in fund_codes:
            try:
                fund = db.query(Fund).filter(Fund.fund_code == fund_code).first()
                if not fund:
                    continue

                # 检查是否已有未过期且有效的数据
                if fund.realtime_data and fund.realtime_data.net_values:
                    try:
                        existing_net_values = json.loads(fund.realtime_data.net_values)
                        if not existing_net_values:
                            print(f"基金 {fund_code} 的历史净值数据为空，需要重新加载")
                        else:
                            updated_at = fund.realtime_data.updated_at
                            if updated_at:
                                now = datetime.now()
                                if (now - updated_at.replace(tzinfo=None)) < timedelta(days=1):
                                    continue
                    except:
                        print(f"基金 {fund_code} 的历史净值数据格式错误，需要重新加载")

                # 从第三方接口获取历史净值数据
                history_data = DataFetcher.get_fund_history(fund_code)

                new_fsrq = history_data.get('fsrq', '')
                new_unit_net_value = history_data.get('unit_net_value', 0)
                new_net_values = history_data.get('net_values', [])

                if not new_net_values:
                    print(f"基金 {fund_code} 获取到的历史净值为空，标记为失败")
                    failed_codes.append(fund_code)
                    continue

                if not fund.realtime_data:
                    fund.realtime_data = FundRealtimeData(fund_id=fund.id)
                fund.realtime_data.net_values = json.dumps(new_net_values)
                fund.realtime_data.one_month_rate = history_data.get('one_month_rate', 0)
                fund.realtime_data.three_month_rate = history_data.get('three_month_rate', 0)
                fund.realtime_data.one_year_rate = history_data.get('one_year_rate', 0)
                fund.realtime_data.daily_change_rate = history_data.get('daily_change_rate', 0)

                fund.realtime_data.fsrq = new_fsrq
                fund.realtime_data.unit_net_value = new_unit_net_value

                fund.realtime_data.updated_at = datetime.now()
                db.commit()

            except Exception as e:
                print(f"预加载基金 {fund_code} 历史净值数据失败: {e}")
                db.rollback()
                failed_codes.append(fund_code)

        success_count = len(fund_codes) - len(failed_codes)
        print(f"[{datetime.now()}] 基金历史净值数据预加载完成: 成功 {success_count}/{len(fund_codes)}，失败 {len(failed_codes)} 个")
    except Exception as e:
        print(f"预加载任务执行失败: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

    return failed_codes

# 添加定时任务：每天凌晨2点预加载历史净值数据
scheduler.add_job(preload_all_funds_history, 'cron', hour=2, minute=0, id='preload_funds_history')

# 辅助函数：判断是否为交易日
def is_trading_day(fsrq: str, allow_yesterday: bool = False) -> bool:
    """
    判断是否为交易日（通过净值日期判断）
    :param fsrq: 净值日期，格式为YYYY-MM-DD
    :param allow_yesterday: 是否允许昨天的净值日期（用于凌晨时段的持仓更新）
    :return: 是否为交易日
    """
    if not fsrq:
        return False
    today = now_cst_naive().strftime('%Y-%m-%d')
    if fsrq == today:
        return True
    if allow_yesterday:
        yesterday = (now_cst_naive() - timedelta(days=1)).strftime('%Y-%m-%d')
        if fsrq == yesterday:
            return True
    return False

# 定时任务：更新持仓收益
@retry_db_operation()
def update_holding_profit():
    """
    定时任务：在交易日晚上7点开始，每10分钟检测一次最新涨幅是否已更新，
    更新所有持仓基金的持有收益到数据库。
    增加凌晨时段(0:00-2:00)，以应对东方财富API延迟发布净值的情况。
    """
    current_time = datetime.now()
    current_hour = current_time.hour

    is_overnight = (0 <= current_hour < 2)
    is_evening = (19 <= current_hour < 23)
    if not (is_evening or is_overnight):
        return

    allow_yesterday = is_overnight

    logger.info(f"开始检查持仓收益更新... (时段: {'凌晨' if is_overnight else '晚间'}, allow_yesterday={allow_yesterday})")
    db = next(get_db())
    try:
        # 获取所有持仓基金
        holdings = db.query(FundHolding).all()
        if not holdings:
            logger.info("没有持仓基金，跳过更新")
            return

        updated_count = 0
        skipped_count = 0

        for holding in holdings:
            fund_code = holding.fund.fund_code

            # 记录更新前的数据
            old_current_value = holding.current_value
            old_profit_loss = holding.profit_loss
            old_profit_loss_rate = holding.profit_loss_rate

            # 获取基金实时数据
            fund_data = get_fund_realtime_data(db, fund_code, force_refresh=True)
            if not fund_data:
                logger.warning(f"基金 {fund_code} 数据获取失败，跳过")
                skipped_count += 1
                continue

            # 检查是否为交易日（fsrq是否为当日，凌晨时段允许昨天的净值日期）
            fsrq = fund_data.get('fsrq', '')
            if not is_trading_day(fsrq, allow_yesterday=allow_yesterday):
                logger.info(f"基金 {fund_code} 净值日期 {fsrq} 不是有效交易日，跳过")
                skipped_count += 1
                continue

            # 检查最新涨幅是否已更新
            daily_change_rate = fund_data.get('daily_change_rate', '-')
            if daily_change_rate == '-' or daily_change_rate == 0:
                logger.info(f"基金 {fund_code} 最新涨幅未更新（当前值: {daily_change_rate}），跳过")
                skipped_count += 1
                continue

            # 根据份额和最新净值计算当前价值
            # 使用份额 × 单位净值来计算当前价值
            unit_net_value = fund_data.get('unit_net_value')
            if not unit_net_value:
                logger.warning(f"基金 {fund_code} 单位净值未获取到，跳过")
                skipped_count += 1
                continue

            # 新的当前价值 = 份额 × 单位净值
            new_current_value = holding.shares * float(unit_net_value)
            new_profit_loss = new_current_value - holding.cost

            # 更新收益率
            new_profit_loss_rate = 0
            if holding.cost > 0:
                new_profit_loss_rate = (new_profit_loss / holding.cost) * 100

            # 更新数据库（添加重试机制）
            @retry_db_operation(max_retries=5, base_delay=0.2)
            def update_holding_data():
                holding.current_value = new_current_value
                holding.profit_loss = new_profit_loss
                holding.profit_loss_rate = new_profit_loss_rate

                # 保存历史记录
                history_record = HoldingProfitHistory(
                    holding_id=holding.id,
                    fund_code=fund_code,
                    cost=holding.cost,
                    shares=holding.shares,
                    avg_cost=holding.avg_cost,
                    current_value=new_current_value,
                    profit_loss=new_profit_loss,
                    profit_loss_rate=new_profit_loss_rate,
                    unit_net_value=float(unit_net_value),
                    fsrq=fsrq,
                    daily_change_rate=float(daily_change_rate) if daily_change_rate != '-' else 0
                )
                db.add(history_record)

                # 同时更新基金历史净值数据，确保历史走势图也更新到今日
                from data_fetcher import DataFetcher
                if fund.realtime_data:
                    history_data = DataFetcher.get_fund_history(fund_code)
                    if history_data:
                        fund.realtime_data.net_values = json.dumps(history_data.get('net_values', []))
                        fund.realtime_data.one_month_rate = history_data.get('one_month_rate', 0)
                        fund.realtime_data.three_month_rate = history_data.get('three_month_rate', 0)
                        fund.realtime_data.one_year_rate = history_data.get('one_year_rate', 0)
                        fund.realtime_data.daily_change_rate = history_data.get('daily_change_rate', 0)
                        fund.realtime_data.fsrq = history_data.get('fsrq', '')
                        fund.realtime_data.unit_net_value = float(unit_net_value)
                        fund.realtime_data.updated_at = datetime.now()
                db.flush()

            update_holding_data()

            updated_count += 1

            # 记录详细的更新日志
            logger.info(f"基金 {fund_code} 持有收益已更新:")
            logger.info(f"  净值日期: {fsrq}")
            logger.info(f"  单位净值: {unit_net_value}")
            logger.info(f"  份额: {holding.shares}")
            logger.info(f"  持仓成本: {holding.cost:.2f}")
            logger.info(f"  当前价值: {old_current_value:.2f} → {new_current_value:.2f}")
            logger.info(f"  盈亏金额: {old_profit_loss:.2f} → {new_profit_loss:.2f}")
            logger.info(f"  盈亏比例: {old_profit_loss_rate:.2f}% → {new_profit_loss_rate:.2f}%")
            logger.info(f"  日涨跌幅: {daily_change_rate}%")

        # 提交事务（添加重试机制）
        @retry_db_operation(max_retries=5, base_delay=0.3)
        def commit_transaction():
            db.commit()

        commit_transaction()
        logger.info(f"持仓收益更新完成: 更新{updated_count}个，跳过{skipped_count}个")
    except Exception as e:
        db.rollback()
        logger.error(f"定时任务执行失败: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

# 定时任务：更新所有基金的历史净值数据
@retry_db_operation()
def update_all_funds_history():
    """
    定时任务：每天更新所有自选基金和持仓基金的历史净值数据
    """
    import time
    print(f"[{datetime.now()}] 开始更新基金历史净值数据...")
    db = next(get_db())
    try:
        # 获取所有需要更新的基金（自选基金 + 持仓基金）
        watchlist_funds = db.query(Watchlist).all()
        holding_funds = db.query(FundHolding).all()

        fund_codes = set()
        for item in watchlist_funds:
            if item.fund:
                fund_codes.add(item.fund.fund_code)
        for holding in holding_funds:
            if holding.fund:
                fund_codes.add(holding.fund.fund_code)

        print(f"需要更新 {len(fund_codes)} 个基金的历史净值数据")

        # 更新每个基金的历史净值数据
        for fund_code in fund_codes:
            try:
                # 强制刷新历史净值数据
                # 使用天级时间戳确保获取最新数据
                timestamp = int(time.time() / 86400)
                history_data = DataFetcher.get_fund_history(fund_code, timestamp)

                # 获取基金对象
                fund = db.query(Fund).filter(Fund.fund_code == fund_code).first()
                if fund:
                    # 更新或创建实时数据记录
                    realtime_data = db.query(FundRealtimeData).filter(FundRealtimeData.fund_id == fund.id).first()
                    if not realtime_data:
                        realtime_data = FundRealtimeData(fund_id=fund.id)
                        db.add(realtime_data)

                    realtime_data.net_values = json.dumps(history_data.get('net_values', []))
                    realtime_data.one_month_rate = history_data.get('one_month_rate', 0)
                    realtime_data.three_month_rate = history_data.get('three_month_rate', 0)
                    realtime_data.one_year_rate = history_data.get('one_year_rate', 0)
                    realtime_data.daily_change_rate = history_data.get('daily_change_rate', 0)
                    realtime_data.fsrq = history_data.get('fsrq', '')
                    realtime_data.unit_net_value = history_data.get('unit_net_value', 0)
                    realtime_data.updated_at = datetime.now()  # 关键：更新 updated_at 字段
                    db.flush()

                print(f"成功更新基金 {fund_code} 的历史净值数据")
            except Exception as e:
                print(f"更新基金 {fund_code} 历史净值数据失败: {e}")

        # 提交事务
        db.commit()
        print(f"[{datetime.now()}] 基金历史净值数据更新完成")
    except Exception as e:
        db.rollback()
        print(f"定时任务执行失败: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

# 添加定时任务：每10分钟执行一次持仓收益更新检查
scheduler.add_job(update_holding_profit, 'interval', minutes=10, id='update_holding_profit')

# 添加定时任务：每天凌晨1点更新基金历史净值数据
scheduler.add_job(update_all_funds_history, 'cron', hour=1, minute=0, id='update_funds_history')

print("定时任务已启动：每10分钟更新一次基金数据")
print("定时任务已启动：每10分钟检查一次持仓收益更新（交易日19:00-23:00）")
print("定时任务已启动：每天凌晨1点更新基金历史净值数据")

# 应用启动时异步预加载历史净值数据
def start_preload_history():
    """
    应用启动时异步预加载所有基金的历史净值数据
    失败后持续重试，直到所有基金预加载成功
    """
    max_total_retries = 5
    for attempt in range(1, max_total_retries + 1):
        print(f"[{datetime.now()}] 预加载第 {attempt}/{max_total_retries} 次尝试...")
        try:
            failed_codes = preload_all_funds_history()
            if not failed_codes:
                print(f"[{datetime.now()}] 历史净值数据预加载全部完成")
                return
            print(f"[{datetime.now()}] 预加载完成，{len(failed_codes)} 个基金失败: {failed_codes}")
        except Exception as e:
            print(f"[{datetime.now()}] 预加载任务执行失败: {e}")
            import traceback
            traceback.print_exc()

        if attempt < max_total_retries:
            delay = 30 * attempt
            print(f"[{datetime.now()}] 等待 {delay} 秒后重试...")
            time.sleep(delay)

    print(f"[{datetime.now()}] 预加载已达最大重试次数 {max_total_retries}，部分基金可能未加载成功")

# 在后台线程中执行预加载，避免阻塞应用启动
# 添加延迟以确保数据库表已完全创建
def delayed_preload():
    print(f"[{datetime.now()}] 进入 delayed_preload 函数...")
    print(f"[{datetime.now()}] 等待2秒，确保数据库表已完全创建...")
    time.sleep(2)
    print(f"[{datetime.now()}] 调用 start_preload_history...")
    start_preload_history()

preload_thread = threading.Thread(target=delayed_preload)
preload_thread.daemon = True
preload_thread.start()
print("历史净值数据预加载任务已在后台启动")

# 辅助函数：获取基金或创建

def get_or_create_fund(db: Session, fund_code: str):
    """
    获取基金信息，如果不存在则创建
    :param db: 数据库会话
    :param fund_code: 基金代码
    :return: 基金对象
    """
    fund = db.query(Fund).filter(Fund.fund_code == fund_code).first()
    if not fund:
        # 从API获取基金信息
        fund_data = DataFetcher.get_fund_valuation(fund_code)
        if fund_data:
            fund = Fund(
                fund_code=fund_data['fund_code'],
                fund_name=fund_data['fund_name'],
                fund_type='未知'
            )
            db.add(fund)
            db.commit()
            db.refresh(fund)
        else:
            # 如果API调用失败，尝试从搜索结果中获取基金信息
            search_results = DataFetcher.search_fund(fund_code)
            if search_results:
                first_result = search_results[0]
                fund = Fund(
                    fund_code=first_result['fund_code'],
                    fund_name=first_result['fund_name'],
                    fund_type=first_result['fund_type']
                )
                db.add(fund)
                db.commit()
                db.refresh(fund)
    return fund


def _merge_fund_data(cached_dict, fresh_data):
    """智能合并基金数据：0值不覆盖非0值，旧日期不覆盖新日期"""
    for fund_code, fresh in fresh_data.items():
        if fund_code not in cached_dict:
            cached_dict[fund_code] = fresh
            continue
        cached = cached_dict[fund_code]

        # 判断日期新旧：如果新数据日期更旧，则涨跌幅类字段不覆盖
        new_fsrq = fresh.get('fsrq', '') or ''
        old_fsrq = cached.get('fsrq', '') or ''

        for key, new_value in fresh.items():
            old_value = cached.get(key)
            if key == 'estimate_change_rate':
                if (new_value == '-' or new_value is None) and old_value and old_value != '-':
                    continue
                if new_value == 0 and old_value and old_value != '-' and old_value != 0:
                    continue
            elif key in ('one_month_rate', 'three_month_rate', 'one_year_rate', 'daily_change_rate'):
                if (new_value == 0 or new_value is None) and old_value and old_value != 0:
                    continue
            if key == 'fsrq':
                if (not new_value or new_value == '') and old_value:
                    continue
                if new_value and old_value and new_value < old_value:
                    continue
            if key == 'unit_net_value':
                if (new_value == 0 or new_value is None or new_value == '') and old_value and old_value != 0:
                    continue
            if key == 'estimate_net_value':
                if (new_value == 0 or new_value is None or new_value == '') and old_value and old_value != 0:
                    continue
            # estimate_time：旧时间不覆盖新时间
            if key == 'estimate_time':
                if (not new_value or new_value == '') and old_value:
                    continue
                if new_value and old_value and new_value < old_value:
                    continue
            cached[key] = new_value


def get_fund_realtime_rates_batch(db: Session, fund_codes: list, force_refresh=False):
    """
    批量并发获取基金实时涨跌幅数据（不获取历史净值数组，用于自选列表）
    :param db: 数据库会话
    :param fund_codes: 基金代码列表
    :param force_refresh: 是否强制刷新
    :return: 基金实时涨跌幅数据字典 {fund_code: data}
    """
    import time
    from datetime import datetime, timedelta
    if not fund_codes:
        return {}

    results = {}

    funds_to_refresh = []
    funds_from_db = {}
    funds_to_get_estimate = []

    fund_map = {}
    realtime_data_map = {}

    funds_query = db.query(Fund).filter(Fund.fund_code.in_(fund_codes)).all()
    for fund in funds_query:
        fund_map[fund.fund_code] = fund

    if funds_query:
        fund_ids = [f.id for f in funds_query]
        rd_query = db.query(FundRealtimeData).filter(FundRealtimeData.fund_id.in_(fund_ids)).all()
        for rd in rd_query:
            for fc, f in fund_map.items():
                if f.id == rd.fund_id:
                    realtime_data_map[fc] = rd
                    break

    now = now_cst_naive()
    is_trading_day = now.weekday() < 5
    is_trading_hours = now.hour >= 9 and now.hour < 15
    # 收盘后时段（15:00-19:00）：需要获取15:00的最终估值
    is_post_trading_hours = now.hour >= 15 and now.hour < 19
    need_estimate_refresh = is_trading_day and (is_trading_hours or is_post_trading_hours)

    for fund_code in fund_codes:
        fund = fund_map.get(fund_code)
        if not fund:
            continue

        realtime_data = realtime_data_map.get(fund_code)

        need_refresh = force_refresh
        rates_all_zero = False
        need_refresh_rates = False
        need_refresh_estimate = False

        if not need_refresh and realtime_data:
            rates_all_zero = (
                (realtime_data.one_month_rate is None or realtime_data.one_month_rate == 0) and
                (realtime_data.three_month_rate is None or realtime_data.three_month_rate == 0) and
                (realtime_data.one_year_rate is None or realtime_data.one_year_rate == 0) and
                (realtime_data.daily_change_rate is None or realtime_data.daily_change_rate == 0)
            )

            if realtime_data.updated_at:
                time_diff = now - realtime_data.updated_at.replace(tzinfo=None)
                if rates_all_zero or time_diff > timedelta(hours=24):
                    need_refresh_rates = True
            else:
                need_refresh_rates = True

            # 晚间时段（19:00-23:00）刷新日涨跌幅数据，但有缓存时间限制
            is_evening_hours = now.hour >= 19 and now.hour < 23
            if is_trading_day and is_evening_hours:
                # 晚间时段：如果数据超过1小时未更新才刷新
                if realtime_data.updated_at:
                    time_diff = now - realtime_data.updated_at.replace(tzinfo=None)
                    if time_diff > timedelta(hours=1):
                        need_refresh_rates = True
                else:
                    need_refresh_rates = True

            # 检查净值日期是否过期（同时检查 fsrq 和 net_value_date）
            if is_trading_day:
                today_str = now.strftime('%Y-%m-%d')
                if now.weekday() == 0:
                    yesterday_str = (now - timedelta(days=3)).strftime('%Y-%m-%d')
                else:
                    yesterday_str = (now - timedelta(days=1)).strftime('%Y-%m-%d')

                # 检查 fsrq 或 net_value_date 是否过期
                current_fsrq = realtime_data.fsrq or realtime_data.net_value_date
                if current_fsrq and current_fsrq != today_str and current_fsrq != yesterday_str:
                    need_refresh_rates = True

            if need_estimate_refresh:
                if realtime_data.updated_at:
                    time_diff = now - realtime_data.updated_at.replace(tzinfo=None)
                    if time_diff > timedelta(seconds=60):
                        need_refresh_estimate = True

                # 收盘后时段（15:00-19:00）：如果缓存的估算时间早于15:00，强制刷新获取最终估值
                if is_post_trading_hours:
                    if realtime_data.estimate_time:
                        try:
                            estimate_time = datetime.strptime(realtime_data.estimate_time, '%Y-%m-%d %H:%M')
                            # 如果估算时间早于当天15:00，强制刷新
                            if estimate_time.hour < 15:
                                need_refresh_estimate = True
                        except:
                            # 解析失败，也强制刷新
                            need_refresh_estimate = True
                    else:
                        # 没有估算时间，强制刷新
                        need_refresh_estimate = True

            if rates_all_zero or need_refresh_rates or need_refresh_estimate:
                need_refresh = True

        print(f"{fund_code}: need_refresh={need_refresh}, need_refresh_rates={need_refresh_rates}, need_refresh_estimate={need_refresh_estimate}")

        if need_refresh:
            funds_to_refresh.append(fund_code)
        elif realtime_data:
            funds_from_db[fund_code] = {
                'fund_code': fund_code,
                'fund_name': fund.fund_name,
                'net_value': realtime_data.fsrq or realtime_data.net_value_date,
                'unit_net_value': realtime_data.unit_net_value,
                'estimate_net_value': realtime_data.estimate_net_value,
                'estimate_change_rate': str(realtime_data.estimate_change_rate) if realtime_data.estimate_change_rate is not None else '-',
                'estimate_time': realtime_data.estimate_time,
                'one_month_rate': realtime_data.one_month_rate,
                'three_month_rate': realtime_data.three_month_rate,
                'one_year_rate': realtime_data.one_year_rate,
                'daily_change_rate': realtime_data.daily_change_rate,
                'fsrq': realtime_data.fsrq,
                'net_values': []
            }
            if need_estimate_refresh or realtime_data.estimate_change_rate is None:
                funds_to_get_estimate.append(fund_code)
            elif is_trading_hours and realtime_data.estimate_time:
                try:
                    etime_date = realtime_data.estimate_time.split(' ')[0]
                    if etime_date != now.strftime('%Y-%m-%d'):
                        funds_to_get_estimate.append(fund_code)
                except:
                    pass
        else:
            funds_to_refresh.append(fund_code)

    cache_key = int(time.time() / 60)
    valuation_data_dict = {}
    rates_data_dict = {}

    funds_always_need_estimate = funds_to_refresh if need_estimate_refresh else []
    funds_conditional_estimate = funds_to_get_estimate if (need_estimate_refresh or len(funds_to_get_estimate) > 0) else []
    all_funds_for_estimate = funds_always_need_estimate + funds_conditional_estimate

    all_funds_for_rates = list(set(funds_to_refresh + funds_conditional_estimate))

    all_funds_to_process = list(set(funds_to_refresh + funds_conditional_estimate))

    from concurrent.futures import ThreadPoolExecutor, as_completed
    if all_funds_for_rates:
        rates_data_dict = DataFetcher.get_fund_rates_batch(all_funds_for_rates, cache_key)

    funds_need_fallback = []
    print(f"funds_to_refresh={funds_to_refresh}, funds_conditional_estimate={funds_conditional_estimate}, all_funds_for_rates={all_funds_for_rates}, rates_data_dict keys={list(rates_data_dict.keys())}")
    for fund_code in all_funds_to_process:
        rates_data = rates_data_dict.get(fund_code)
        if not rates_data or (rates_data.get('one_month_rate') == 0 and rates_data.get('three_month_rate') == 0 and rates_data.get('one_year_rate') == 0 and rates_data.get('daily_change_rate') == 0):
            funds_need_fallback.append(fund_code)

    if funds_need_fallback:
        print(f"以下基金使用 get_fund_rates 获取数据失败，并发尝试 _get_fund_rates_no_retry: {funds_need_fallback}")
        from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError
        fallback_results = {}
        with ThreadPoolExecutor(max_workers=5) as executor:
            future_to_fund = {
                executor.submit(DataFetcher._get_fund_rates_no_retry, fc, cache_key): fc
                for fc in funds_need_fallback
            }
            try:
                for future in as_completed(future_to_fund, timeout=15):
                    fc = future_to_fund[future]
                    try:
                        fallback_results[fc] = future.result(timeout=8)
                    except Exception as e:
                        print(f"_get_fund_history_simple_no_retry 获取基金 {fc} 数据失败: {e}")
            except TimeoutError:
                print(f"fallback请求超时，已获取 {len(fallback_results)} 个，剩余 {len(funds_need_fallback) - len(fallback_results)} 个未完成")
                # 超时情况下，继续处理已完成的任务
                for future in future_to_fund:
                    if future.done():
                        fc = future_to_fund[future]
                        if fc not in fallback_results:
                            try:
                                fallback_results[fc] = future.result()
                            except Exception as e:
                                print(f"获取超时任务 {fc} 结果失败: {e}")

        for fc in funds_need_fallback:
            history_data = fallback_results.get(fc)
            if history_data:
                rates_data_dict[fc] = {
                    'fund_code': fc,
                    'one_month_rate': history_data.get('one_month_rate', 0),
                    'three_month_rate': history_data.get('three_month_rate', 0),
                    'one_year_rate': history_data.get('one_year_rate', 0),
                    'daily_change_rate': history_data.get('daily_change_rate', 0),
                    'estimate_change_rate': history_data.get('estimate_change_rate', 0),
                    'fsrq': history_data.get('fsrq', ''),
                    'unit_net_value': history_data.get('unit_net_value', 0)
                }

    # 处理数据并更新数据库
    for fund_code in all_funds_to_process:
        fund = fund_map.get(fund_code)
        if not fund:
            continue

        fund_data = valuation_data_dict.get(fund_code)
        rates_data = rates_data_dict.get(fund_code)
        realtime_data = realtime_data_map.get(fund_code)

        # 检查获取的数据是否有效
        has_valid_estimate = fund_data and (fund_data.get('estimate_net_value') or fund_data.get('estimate_change_rate'))
        has_valid_rates = rates_data and any([
            rates_data.get('one_month_rate', 0) != 0,
            rates_data.get('three_month_rate', 0) != 0,
            rates_data.get('one_year_rate', 0) != 0,
            rates_data.get('daily_change_rate', 0) != 0,
            rates_data.get('unit_net_value', 0) != 0,
            rates_data.get('fsrq', '') != ''
        ])

        # 如果获取的数据无效且数据库中已有数据，跳过更新
        if not has_valid_estimate and not has_valid_rates:
            if realtime_data:
                # 使用缓存的数据
                data = {
                    'fund_code': fund_code,
                    'fund_name': fund.fund_name,
                    'net_value_date': realtime_data.net_value_date,
                    'unit_net_value': realtime_data.unit_net_value,
                    'estimate_net_value': realtime_data.estimate_net_value,
                    'estimate_change_rate': realtime_data.estimate_change_rate,
                    'estimate_time': realtime_data.estimate_time,
                    'one_month_rate': realtime_data.one_month_rate,
                    'three_month_rate': realtime_data.three_month_rate,
                    'one_year_rate': realtime_data.one_year_rate,
                    'daily_change_rate': realtime_data.daily_change_rate,
                    'fsrq': realtime_data.fsrq,
                    'net_values': '[]'
                }
            else:
                continue
        else:
            # 准备数据
            net_value_date = ''
            if rates_data:
                net_value_date = rates_data.get('fsrq', '')
            elif fund_data:
                net_value_date = fund_data.get('net_value', '')

            unit_net_value = None
            if rates_data and rates_data.get('unit_net_value') is not None and rates_data.get('unit_net_value') != '' and rates_data.get('unit_net_value') != 0:
                unit_net_value = float(rates_data.get('unit_net_value'))
            elif fund_data and fund_data.get('unit_net_value') is not None and fund_data.get('unit_net_value') != '':
                unit_net_value = float(fund_data.get('unit_net_value'))

            estimate_net_value = None
            if fund_data and fund_data.get('estimate_net_value') is not None and fund_data.get('estimate_net_value') != '':
                estimate_net_value = float(fund_data.get('estimate_net_value'))
            elif rates_data and rates_data.get('estimate_net_value') is not None and rates_data.get('estimate_net_value') != '':
                estimate_net_value = float(rates_data.get('estimate_net_value'))

            estimate_change_rate = None
            if fund_data and fund_data.get('estimate_change_rate') is not None and fund_data.get('estimate_change_rate') != '':
                estimate_change_rate = float(fund_data.get('estimate_change_rate'))

            estimate_time = ''
            if fund_data:
                estimate_time = fund_data.get('estimate_time', '')
            if not estimate_time and rates_data:
                estimate_time = rates_data.get('estimate_time', '')

            # 获取涨跌幅数据，如果API返回0值且数据库有非0缓存，保留缓存值
            one_month_rate = rates_data.get('one_month_rate', 0) if rates_data else 0
            three_month_rate = rates_data.get('three_month_rate', 0) if rates_data else 0
            one_year_rate = rates_data.get('one_year_rate', 0) if rates_data else 0
            daily_change_rate = rates_data.get('daily_change_rate', 0) if rates_data else 0
            rates_estimate_change_rate = rates_data.get('estimate_change_rate', 0) if rates_data else 0
            fsrq = rates_data.get('fsrq', '') if rates_data else ''

            # estimate_change_rate: 只有当rates_data中有确认的实际涨跌幅(daily_change_rate)时，才清除估值
            # 如果只是estimate_change_rate为0但没有实际涨跌幅，保留估值接口的数据
            if rates_estimate_change_rate == 0 and daily_change_rate != 0:
                estimate_change_rate = 0
            elif estimate_change_rate is None and rates_estimate_change_rate:
                estimate_change_rate = float(rates_estimate_change_rate)

            if realtime_data:
                # 按字段保留数据库缓存值：API返回0/空时保留数据库中的非0/非空值
                if one_month_rate == 0 and realtime_data.one_month_rate:
                    one_month_rate = realtime_data.one_month_rate
                if three_month_rate == 0 and realtime_data.three_month_rate:
                    three_month_rate = realtime_data.three_month_rate
                if one_year_rate == 0 and realtime_data.one_year_rate:
                    one_year_rate = realtime_data.one_year_rate
                if daily_change_rate == 0 and realtime_data.daily_change_rate:
                    daily_change_rate = realtime_data.daily_change_rate
                if not fsrq and realtime_data.fsrq:
                    fsrq = realtime_data.fsrq
                if unit_net_value is None and realtime_data.unit_net_value:
                    unit_net_value = realtime_data.unit_net_value

            data = {
                'fund_code': fund_code,
                'fund_name': fund.fund_name,
                'net_value_date': net_value_date,
                'unit_net_value': unit_net_value,
                'estimate_net_value': estimate_net_value,
                'estimate_change_rate': estimate_change_rate,
                'estimate_time': estimate_time,
                'one_month_rate': one_month_rate,
                'three_month_rate': three_month_rate,
                'one_year_rate': one_year_rate,
                'daily_change_rate': daily_change_rate,
                'fsrq': fsrq,
                'net_values': '[]'
            }

        if realtime_data:
            for key, value in data.items():
                if key in ('fund_code', 'fund_name'):
                    continue
                if key in ('estimate_net_value', 'estimate_change_rate', 'estimate_time') and value is None:
                    continue
                if key == 'estimate_time' and value == '':
                    continue
                if key in ('one_month_rate', 'three_month_rate', 'one_year_rate', 'daily_change_rate', 'unit_net_value'):
                    old_value = getattr(realtime_data, key, None)
                    if (value == 0 or value is None) and old_value and old_value != 0:
                        continue
                if key == 'estimate_change_rate':
                    old_ecr = getattr(realtime_data, 'estimate_change_rate', None)
                    # 0值（净值已确认）不应被旧估算值覆盖，但新交易日的估值应允许写入
                    # 只有当旧值非0且新值为0/None时才跳过
                    if old_ecr and old_ecr != 0 and (value == 0 or value is None):
                        continue
                if key == 'fsrq':
                    if (not value or value == '') and getattr(realtime_data, 'fsrq', None):
                        continue
                    existing_fsrq = getattr(realtime_data, 'fsrq', None)
                    if value and existing_fsrq and value < existing_fsrq:
                        continue
                if key == 'net_value_date':
                    existing_nvd = getattr(realtime_data, 'net_value_date', None)
                    if value and existing_nvd and value < existing_nvd:
                        continue
                setattr(realtime_data, key, value)
            realtime_data.updated_at = datetime.now()  # 更新时间戳
        else:
            realtime_data = FundRealtimeData(
                fund_id=fund.id,
                net_value_date=data['net_value_date'],
                unit_net_value=data['unit_net_value'],
                estimate_net_value=data['estimate_net_value'],
                estimate_change_rate=data['estimate_change_rate'],
                estimate_time=data['estimate_time'],
                one_month_rate=data['one_month_rate'],
                three_month_rate=data['three_month_rate'],
                one_year_rate=data['one_year_rate'],
                daily_change_rate=data['daily_change_rate'],
                fsrq=data['fsrq'],
                net_values=data['net_values']
            )
            db.add(realtime_data)

        result_estimate_net_value = data.get('estimate_net_value', None)
        if result_estimate_net_value is None and realtime_data and realtime_data.estimate_net_value is not None:
            result_estimate_net_value = realtime_data.estimate_net_value

        result_estimate_change_rate = data.get('estimate_change_rate', None)
        if result_estimate_change_rate is None and realtime_data and realtime_data.estimate_change_rate is not None:
            result_estimate_change_rate = realtime_data.estimate_change_rate

        result_estimate_time = data.get('estimate_time', '')
        if not result_estimate_time and realtime_data and realtime_data.estimate_time:
            result_estimate_time = realtime_data.estimate_time

        # 添加到结果（延迟flush到循环外批量提交）
        result_data = {
            'fund_code': fund_code,
            'fund_name': fund.fund_name,
            'net_value': data.get('fsrq', ''),
            'unit_net_value': data.get('unit_net_value', None),
            'estimate_net_value': result_estimate_net_value,
            'estimate_change_rate': str(result_estimate_change_rate) if result_estimate_change_rate is not None else '-',
            'estimate_time': result_estimate_time,
            'one_month_rate': data.get('one_month_rate', 0),
            'three_month_rate': data.get('three_month_rate', 0),
            'one_year_rate': data.get('one_year_rate', 0),
            'daily_change_rate': data.get('daily_change_rate', 0),
            'fsrq': data.get('fsrq', ''),
            'net_values': []
        }
        results[fund_code] = result_data
        logger.info(f"[rates_batch] {fund_code}: fsrq={data.get('fsrq','')}, daily_change_rate={data.get('daily_change_rate',0)}, estimate_change_rate={result_estimate_change_rate}, unit_net_value={data.get('unit_net_value',None)}")

    try:
        db.commit()
    except Exception as e:
        print(f"批量提交数据库更新失败: {e}")
        db.rollback()

    # 合并数据库中的数据（只填充API未返回的数据）
    for fund_code, data in funds_from_db.items():
        if fund_code not in results:
            results[fund_code] = data

    # 用最新的API估值数据更新结果
    for fund_code in funds_to_get_estimate:
        if fund_code in valuation_data_dict and fund_code in results:
            fund_data = valuation_data_dict[fund_code]
            if fund_data:
                estimate_net_value = None
                if fund_data.get('estimate_net_value') is not None and fund_data.get('estimate_net_value') != '':
                    estimate_net_value = float(fund_data.get('estimate_net_value'))

                estimate_change_rate = None
                if fund_data.get('estimate_change_rate') is not None and fund_data.get('estimate_change_rate') != '':
                    estimate_change_rate = float(fund_data.get('estimate_change_rate'))

                estimate_time = fund_data.get('estimate_time', '')

                current_daily = results[fund_code].get('daily_change_rate', 0)
                current_fsrq = results[fund_code].get('fsrq', '')
                current_estimate = results[fund_code].get('estimate_change_rate', '-')
                today_str_check = now_cst_naive().strftime('%Y-%m-%d')
                is_after_close = now_cst_naive().hour >= 15
                rates_confirmed = (is_after_close and current_daily != 0 and
                                   current_fsrq == today_str_check)

                if rates_confirmed:
                    # 净值已确认，只更新estimate_time，不覆盖estimate_change_rate和net_value
                    results[fund_code]['estimate_time'] = estimate_time
                    realtime_data = realtime_data_map.get(fund_code)
                    if realtime_data:
                        if estimate_time:
                            realtime_data.estimate_time = estimate_time
                        realtime_data.updated_at = datetime.now()
                        try:
                            db.commit()
                        except Exception as e:
                            print(f"更新估值缓存到数据库失败: {e}")
                            db.rollback()
                else:
                    # 净值未确认，使用估值接口数据
                    net_value = fund_data.get('net_value', '')
                    if net_value:
                        results[fund_code]['net_value'] = net_value

                    results[fund_code]['estimate_net_value'] = estimate_net_value
                    results[fund_code]['estimate_change_rate'] = str(estimate_change_rate) if estimate_change_rate is not None else '-'
                    results[fund_code]['estimate_time'] = estimate_time

                    realtime_data = realtime_data_map.get(fund_code)
                    if realtime_data:
                        if estimate_net_value is not None:
                            realtime_data.estimate_net_value = estimate_net_value
                        if estimate_change_rate is not None:
                            realtime_data.estimate_change_rate = estimate_change_rate
                        if estimate_time:
                            realtime_data.estimate_time = estimate_time
                        realtime_data.updated_at = datetime.now()
                        try:
                            db.commit()
                        except Exception as e:
                            print(f"更新估值缓存到数据库失败: {e}")
                            db.rollback()

    return results

def get_fund_realtime_rates(db: Session, fund_code: str, force_refresh=False):
    """
    获取基金实时涨跌幅数据（不获取历史净值数组，用于自选列表）
    :param db: 数据库会话
    :param fund_code: 基金代码
    :param force_refresh: 是否强制刷新
    :return: 基金实时涨跌幅数据字典
    """
    from datetime import datetime, timedelta
    fund = None
    realtime_data = None

    # 尝试从数据库获取基金信息
    try:
        fund = db.query(Fund).filter(Fund.fund_code == fund_code).first()
        if fund:
            realtime_data = db.query(FundRealtimeData).filter(FundRealtimeData.fund_id == fund.id).first()
    except Exception as e:
        print(f"数据库查询失败: {e}")

    # 如果强制刷新或数据不存在或数据过期（超过10分钟），则从API获取
    need_refresh = force_refresh
    fund_data = None
    rates_data = None

    # 无论是否有数据库数据，都尝试从API获取数据
    # 因为数据库可能连接失败，或者数据过期
    cache_key = int(time.time() / 60)
    print(f"获取基金 {fund_code} 数据，缓存键: {cache_key}")
    fund_data = DataFetcher.get_fund_valuation(fund_code, cache_key)
    print(f"基金 {fund_code} 估值数据: {fund_data}")
    rates_data = DataFetcher.get_fund_rates(fund_code, cache_key)
    print(f"基金 {fund_code} 涨跌幅数据: {rates_data}")

    # 只要有数据，就处理
    if fund_data or rates_data:
        # 准备数据
        fund_name = fund.fund_name if fund else fund_code
        net_value_date = ''
        if fund_data:
            net_value_date = fund_data.get('net_value', '')
        elif rates_data:
            net_value_date = rates_data.get('fsrq', '')

        unit_net_value = None
        if fund_data and fund_data.get('unit_net_value') is not None and fund_data.get('unit_net_value') != '':
            unit_net_value = float(fund_data.get('unit_net_value'))

        estimate_net_value = None
        if fund_data and fund_data.get('estimate_net_value') is not None and fund_data.get('estimate_net_value') != '':
            estimate_net_value = float(fund_data.get('estimate_net_value'))

        estimate_change_rate = None
        if fund_data and fund_data.get('estimate_change_rate') is not None and fund_data.get('estimate_change_rate') != '':
            estimate_change_rate = float(fund_data.get('estimate_change_rate'))

        estimate_time = ''
        if fund_data:
            estimate_time = fund_data.get('estimate_time', '')

        one_month_rate = 0
        three_month_rate = 0
        one_year_rate = 0
        daily_change_rate = 0
        fsrq = ''
        if rates_data:
            one_month_rate = rates_data.get('one_month_rate', 0)
            three_month_rate = rates_data.get('three_month_rate', 0)
            one_year_rate = rates_data.get('one_year_rate', 0)
            daily_change_rate = rates_data.get('daily_change_rate', 0)
            fsrq = rates_data.get('fsrq', '')

        data = {
            'fund_code': fund_code,
            'fund_name': fund_name,
            'net_value_date': net_value_date,
            'unit_net_value': unit_net_value,
            'estimate_net_value': estimate_net_value,
            'estimate_change_rate': estimate_change_rate,
            'estimate_time': estimate_time,
            'one_month_rate': one_month_rate,
            'three_month_rate': three_month_rate,
            'one_year_rate': one_year_rate,
            'daily_change_rate': daily_change_rate,
            'fsrq': fsrq,
            'net_values': '[]'  # 不存储历史净值数组
        }
        print(f"准备更新基金 {fund_code} 数据: {data}")

        # 尝试更新或创建数据库记录（添加重试机制）
        try:
            if fund:
                @retry_db_operation(max_retries=5, base_delay=0.2)
                def update_realtime_data():
                    import time
                    if realtime_data:
                        for key, value in data.items():
                            if key != 'fund_code' and key != 'fund_name':
                                setattr(realtime_data, key, value)
                    else:
                        new_realtime_data = FundRealtimeData(
                            fund_id=fund.id,
                            net_value_date=data['net_value_date'],
                            unit_net_value=data['unit_net_value'],
                            estimate_net_value=data['estimate_net_value'],
                            estimate_change_rate=data['estimate_change_rate'],
                            estimate_time=data['estimate_time'],
                            one_month_rate=data['one_month_rate'],
                            three_month_rate=data['three_month_rate'],
                            one_year_rate=data['one_year_rate'],
                            daily_change_rate=data['daily_change_rate'],
                            fsrq=data['fsrq'],
                            net_values=data['net_values']
                        )
                        db.add(new_realtime_data)
                        return new_realtime_data
                    # 添加死锁处理和重试机制
                    max_retries = 3
                    for attempt in range(max_retries):
                        try:
                            db.flush()
                            db.refresh(realtime_data)
                            break
                        except Exception as e:
                            if attempt < max_retries - 1:
                                print(f"数据库更新失败，第{attempt + 1}次重试... 错误: {e}")
                                db.rollback()
                                time.sleep(0.1 * (attempt + 1))
                            else:
                                print(f"数据库更新失败，已达到最大重试次数{max_retries}次。错误: {e}")
                                db.rollback()
                                raise
                    return realtime_data

                realtime_data = update_realtime_data()
        except Exception as e:
            print(f"数据库操作失败，继续返回API数据: {e}")
            # 数据库操作失败，仍然返回API数据

        # 返回API数据
        result = {
            'fund_code': fund_code,
            'fund_name': fund_name,
            'net_value': data.get('net_value_date', ''),
            'unit_net_value': data.get('unit_net_value', None),
            'estimate_net_value': data.get('estimate_net_value', None),
            'estimate_change_rate': str(data.get('estimate_change_rate', 0)) if data.get('estimate_change_rate') is not None else '-',
            'estimate_time': data.get('estimate_time', ''),
            'one_month_rate': data.get('one_month_rate', 0),
            'three_month_rate': data.get('three_month_rate', 0),
            'one_year_rate': data.get('one_year_rate', 0),
            'daily_change_rate': data.get('daily_change_rate', 0),
            'fsrq': data.get('fsrq', ''),
            'net_values': []
        }
        print(f"基金 {fund_code} 返回API数据: {result}")
        return result
    else:
        # API调用失败，尝试返回数据库中的旧数据（如果有）
        if fund and realtime_data:
            # 返回数据库中的旧数据
            print(f"基金 {fund_code} API调用失败，返回数据库旧数据")
            return {
                'fund_code': fund_code,
                'fund_name': fund.fund_name,
                'net_value': realtime_data.net_value_date if realtime_data else '',
                'unit_net_value': realtime_data.unit_net_value if realtime_data else None,
                'estimate_net_value': realtime_data.estimate_net_value if realtime_data else None,
                'estimate_change_rate': str(realtime_data.estimate_change_rate) if realtime_data and realtime_data.estimate_change_rate is not None else '-',
                'estimate_time': realtime_data.estimate_time if realtime_data else '',
                'one_month_rate': realtime_data.one_month_rate if realtime_data else 0,
                'three_month_rate': realtime_data.three_month_rate if realtime_data else 0,
                'one_year_rate': realtime_data.one_year_rate if realtime_data else 0,
                'daily_change_rate': realtime_data.daily_change_rate if realtime_data else 0,
                'fsrq': realtime_data.fsrq if realtime_data else '',
                'net_values': []
            }
        else:
            # 如果数据库中也没有数据，返回基本信息
            print(f"基金 {fund_code} API调用失败，返回默认数据")
            return {
                'fund_code': fund_code,
                'fund_name': fund.fund_name if fund else fund_code,
                'net_value': '',
                'unit_net_value': None,
                'estimate_net_value': None,
                'estimate_change_rate': '-',
                'estimate_time': '',
                'one_month_rate': 0,
                'three_month_rate': 0,
                'one_year_rate': 0,
                'daily_change_rate': 0,
                'fsrq': '',
                'net_values': []
            }

def get_fund_realtime_data(db: Session, fund_code: str, force_refresh=False, need_history_data=True, skip_db_write=False):
    """
    获取基金实时数据，优先从数据库读取
    :param db: 数据库会话
    :param fund_code: 基金代码
    :param force_refresh: 是否强制刷新
    :param need_history_data: 是否需要获取历史净值数据（默认需要）
    :param skip_db_write: 是否跳过数据库写入操作（默认False）
    :return: 基金实时数据字典
    """
    from datetime import datetime, timedelta
    fund = db.query(Fund).filter(Fund.fund_code == fund_code).first()
    if not fund:
        return None

    # 检查数据库中是否有实时数据
    realtime_data = db.query(FundRealtimeData).filter(FundRealtimeData.fund_id == fund.id).first()

    # 如果强制刷新或数据不存在，则从API获取
    need_refresh = force_refresh
    fund_data = None
    history_data = None
    if not need_refresh and realtime_data:
        # 检查涨跌幅数据是否有效 - 只检查涨跌幅数据，不包括估算数据
        # 估算数据是单独刷新的，不应该作为涨跌幅数据有效性的判断依据
        rates_valid = (
            (realtime_data.one_month_rate is not None and realtime_data.one_month_rate != 0) or
            (realtime_data.three_month_rate is not None and realtime_data.three_month_rate != 0) or
            (realtime_data.one_year_rate is not None and realtime_data.one_year_rate != 0) or
            (realtime_data.daily_change_rate is not None and realtime_data.daily_change_rate != 0)
        )

        # 检查是否需要刷新不同类型的数据
        need_refresh_rates = False
        need_refresh_estimate = False

        now = now_cst_naive()
        is_weekday = now.weekday() < 5

        # 检查最新涨幅、近1月、3月、1年的涨幅是否需要刷新（24小时）
        if realtime_data.updated_at:
            now = now_cst_naive()
            time_diff = now - realtime_data.updated_at.replace(tzinfo=None)
            if time_diff > timedelta(hours=24):
                need_refresh_rates = True

        if is_weekday and realtime_data.fsrq:
            today_str = now.strftime('%Y-%m-%d')
            if now.weekday() == 0:
                yesterday_str = (now - timedelta(days=3)).strftime('%Y-%m-%d')
            else:
                yesterday_str = (now - timedelta(days=1)).strftime('%Y-%m-%d')
            if realtime_data.fsrq != today_str and realtime_data.fsrq != yesterday_str:
                need_refresh_rates = True

        now = now_cst_naive()
        is_trading_day = now.weekday() < 5
        is_trading_hours = now.hour >= 9 and now.hour < 15
        is_evening_hours = now.hour >= 19 and now.hour < 23

        if is_trading_day and is_trading_hours:
            if realtime_data.updated_at:
                time_diff = now - realtime_data.updated_at.replace(tzinfo=None)
                if time_diff > timedelta(seconds=60):
                    need_refresh_estimate = True
        else:
            # 非交易日或非交易时间，不需要刷新估算涨幅
            need_refresh_estimate = False

        # 晚间时段（19:00-23:00）是基金净值和日涨幅发布时间，需要强制刷新日涨幅数据
        if is_trading_day and is_evening_hours:
            need_refresh_rates = True

        # 如果涨跌幅数据无效，或者需要刷新涨跌幅，或者需要刷新估算，就整体刷新
        if need_refresh_rates or need_refresh_estimate or not rates_valid:
            need_refresh = True

    if need_refresh:
        # 从API获取数据
        fund_data = DataFetcher.get_fund_valuation(fund_code, int(time.time()))

        if need_history_data:
            history_data = DataFetcher.get_fund_history(fund_code)
        else:
            history_data = DataFetcher.get_fund_history_simple(fund_code)

        # 即使fund_data为None，只要history_data有数据，就处理
        if history_data:
            # 准备数据
            data = {
                'fund_code': fund_code,
                'fund_name': fund.fund_name,
                'net_value_date': fund_data.get('net_value') if fund_data else history_data.get('fsrq', ''),
                'unit_net_value': float(history_data.get('unit_net_value', 0)) if history_data and history_data.get('unit_net_value') else (float(fund_data.get('unit_net_value', 0)) if fund_data and fund_data.get('unit_net_value') else None),
                'estimate_net_value': float(fund_data.get('estimate_net_value', 0)) if fund_data and fund_data.get('estimate_net_value') else None,
                'estimate_change_rate': float(fund_data.get('estimate_change_rate', 0)) if fund_data and fund_data.get('estimate_change_rate') else None,
                'estimate_time': fund_data.get('estimate_time', '') if fund_data else '',
                'one_month_rate': history_data.get('one_month_rate', 0),
                'three_month_rate': history_data.get('three_month_rate', 0),
                'one_year_rate': history_data.get('one_year_rate', 0),
                'daily_change_rate': history_data.get('daily_change_rate', 0),
                'fsrq': history_data.get('fsrq', '')
            }

            # 按字段保留数据库缓存值：API返回0/空时保留数据库中的非0/非空值
            if realtime_data:
                if data.get('one_month_rate', 0) == 0 and realtime_data.one_month_rate:
                    data['one_month_rate'] = realtime_data.one_month_rate
                if data.get('three_month_rate', 0) == 0 and realtime_data.three_month_rate:
                    data['three_month_rate'] = realtime_data.three_month_rate
                if data.get('one_year_rate', 0) == 0 and realtime_data.one_year_rate:
                    data['one_year_rate'] = realtime_data.one_year_rate
                if data.get('daily_change_rate', 0) == 0 and realtime_data.daily_change_rate:
                    data['daily_change_rate'] = realtime_data.daily_change_rate
                if not data.get('fsrq', '') and realtime_data.fsrq:
                    data['fsrq'] = realtime_data.fsrq
                if data.get('unit_net_value') is None and realtime_data.unit_net_value:
                    data['unit_net_value'] = realtime_data.unit_net_value

            if need_history_data:
                data['net_values'] = json.dumps(history_data.get('net_values', []))
            elif realtime_data and realtime_data.net_values:
                # 不需要完整历史数据但数据库中有值时，保留原值
                data['net_values'] = realtime_data.net_values
            else:
                # 数据库中也没有值时，设置为空数组
                data['net_values'] = json.dumps([])

            if not skip_db_write:
                if realtime_data:
                    for key, value in data.items():
                        if key in ('fund_code', 'fund_name'):
                            continue
                        if key == 'net_values' and not need_history_data:
                            continue
                        if key in ('one_month_rate', 'three_month_rate', 'one_year_rate', 'daily_change_rate', 'unit_net_value'):
                            old_value = getattr(realtime_data, key, None)
                            if (value == 0 or value is None) and old_value and old_value != 0:
                                continue
                        if key == 'fsrq' and (not value or value == '') and getattr(realtime_data, 'fsrq', None):
                            continue
                        setattr(realtime_data, key, value)
                else:
                    realtime_data = FundRealtimeData(
                        fund_id=fund.id,
                        net_value_date=data['net_value_date'],
                        unit_net_value=data['unit_net_value'],
                        estimate_net_value=data['estimate_net_value'],
                        estimate_change_rate=data['estimate_change_rate'],
                        estimate_time=data['estimate_time'],
                        one_month_rate=data['one_month_rate'],
                        three_month_rate=data['three_month_rate'],
                        one_year_rate=data['one_year_rate'],
                        daily_change_rate=data['daily_change_rate'],
                        fsrq=data['fsrq'],
                        net_values=data['net_values']
                    )
                    db.add(realtime_data)

                # 添加死锁处理和重试机制
                max_retries = 3
                for attempt in range(max_retries):
                    try:
                        db.flush()
                        db.refresh(realtime_data)
                        break
                    except Exception as e:
                        if attempt < max_retries - 1:
                            print(f"数据库更新失败，第{attempt + 1}次重试... 错误: {e}")
                            db.rollback()
                            time.sleep(0.1 * (attempt + 1))
                        else:
                            print(f"数据库更新失败，已达到最大重试次数{max_retries}次。错误: {e}")
                            db.rollback()
                            raise
        else:
            # API调用失败，尝试使用 get_fund_rates 方法获取数据
            print(f"基金 {fund_code} API调用失败，尝试使用 get_fund_rates 方法获取数据")
            rates_data = DataFetcher.get_fund_rates(fund_code)
            if rates_data:
                # 准备数据
                data = {
                    'fund_code': fund_code,
                    'fund_name': fund.fund_name,
                    'net_value_date': rates_data.get('fsrq', ''),
                    'unit_net_value': float(rates_data.get('unit_net_value', 0)) if rates_data.get('unit_net_value') else None,
                    'estimate_net_value': None,
                    'estimate_change_rate': None,
                    'estimate_time': '',
                    'one_month_rate': rates_data.get('one_month_rate', 0),
                    'three_month_rate': rates_data.get('three_month_rate', 0),
                    'one_year_rate': rates_data.get('one_year_rate', 0),
                    'daily_change_rate': rates_data.get('daily_change_rate', 0),
                    'fsrq': rates_data.get('fsrq', '')
                }

                # 只有需要完整历史数据时才更新 net_values，否则保留数据库中的值
                if need_history_data:
                    data['net_values'] = json.dumps([])
                elif realtime_data and realtime_data.net_values:
                    # 不需要完整历史数据但数据库中有值时，保留原值
                    data['net_values'] = realtime_data.net_values
                else:
                    # 数据库中也没有值时，设置为空数组
                    data['net_values'] = json.dumps([])

                if not skip_db_write:
                    if realtime_data:
                        for key, value in data.items():
                            if key in ('fund_code', 'fund_name'):
                                continue
                            if key == 'net_values' and not need_history_data:
                                continue
                            setattr(realtime_data, key, value)
                    else:
                        realtime_data = FundRealtimeData(
                            fund_id=fund.id,
                            net_value_date=data['net_value_date'],
                            unit_net_value=data['unit_net_value'],
                            estimate_net_value=data['estimate_net_value'],
                            estimate_change_rate=data['estimate_change_rate'],
                            estimate_time=data['estimate_time'],
                            one_month_rate=data['one_month_rate'],
                            three_month_rate=data['three_month_rate'],
                            one_year_rate=data['one_year_rate'],
                            daily_change_rate=data['daily_change_rate'],
                            fsrq=data['fsrq'],
                            net_values=data['net_values']
                        )
                        db.add(realtime_data)

                    # 添加死锁处理和重试机制
                    max_retries = 3
                    for attempt in range(max_retries):
                        try:
                            db.flush()
                            db.refresh(realtime_data)
                            break
                        except Exception as e:
                            if attempt < max_retries - 1:
                                print(f"数据库更新失败，第{attempt + 1}次重试... 错误: {e}")
                                db.rollback()
                                time.sleep(0.1 * (attempt + 1))
                            else:
                                print(f"数据库更新失败，已达到最大重试次数{max_retries}次。错误: {e}")
                                db.rollback()
                                raise

                # 不直接返回，而是继续执行，让函数统一处理返回逻辑
                pass
            else:
                # API调用失败，返回数据库中的旧数据（如果有）
                if not realtime_data:
                    # 如果数据库中也没有数据，返回基本信息
                    return {
                        'fund_code': fund_code,
                        'fund_name': fund.fund_name,
                        'net_value': '',
                        'unit_net_value': None,
                        'estimate_net_value': None,
                        'estimate_change_rate': '-',
                        'estimate_time': '',
                        'one_month_rate': 0,
                        'three_month_rate': 0,
                        'one_year_rate': 0,
                        'daily_change_rate': 0,
                        'fsrq': '',
                        'net_values': []
                    }
    else:
        # 从数据库读取数据
        if not realtime_data:
            # 如果数据库中也没有数据，返回基本信息
            return {
                'fund_code': fund_code,
                'fund_name': fund.fund_name,
                'net_value': '',
                'unit_net_value': None,
                'estimate_net_value': None,
                'estimate_change_rate': '-',
                'estimate_time': '',
                'one_month_rate': 0,
                'three_month_rate': 0,
                'one_year_rate': 0,
                'daily_change_rate': 0,
                'fsrq': '',
                'net_values': []
            }

        data = {
            'fund_code': fund_code,
            'fund_name': fund.fund_name,
            'net_value': realtime_data.net_value_date,
            'unit_net_value': realtime_data.unit_net_value,
            'estimate_net_value': realtime_data.estimate_net_value,
            'estimate_change_rate': realtime_data.estimate_change_rate,
            'estimate_time': realtime_data.estimate_time,
            'one_month_rate': realtime_data.one_month_rate,
            'three_month_rate': realtime_data.three_month_rate,
            'one_year_rate': realtime_data.one_year_rate,
            'daily_change_rate': realtime_data.daily_change_rate,
            'fsrq': realtime_data.fsrq,
            'net_values': json.loads(realtime_data.net_values) if realtime_data.net_values else []
        }

    # 返回格式化的数据
    if need_refresh and ('data' in locals()):
        # 如果刚从API获取了数据，使用data变量
        return {
            'fund_code': fund_code,
            'fund_name': fund.fund_name,
            'net_value': data.get('net_value_date', ''),
            'unit_net_value': data.get('unit_net_value', None),
            'estimate_net_value': data.get('estimate_net_value', None),
            'estimate_change_rate': str(data.get('estimate_change_rate', 0)) if data.get('estimate_change_rate') is not None else '-',
            'estimate_time': data.get('estimate_time', ''),
            'one_month_rate': data.get('one_month_rate', 0),
            'three_month_rate': data.get('three_month_rate', 0),
            'one_year_rate': data.get('one_year_rate', 0),
            'daily_change_rate': data.get('daily_change_rate', 0),
            'fsrq': data.get('fsrq', ''),
            'net_values': json.loads(data.get('net_values', '[]'))
        }
    else:
        # 否则使用realtime_data
        return {
            'fund_code': fund_code,
            'fund_name': fund.fund_name,
            'net_value': realtime_data.net_value_date if realtime_data else '',
            'unit_net_value': realtime_data.unit_net_value if realtime_data else None,
            'estimate_net_value': realtime_data.estimate_net_value if realtime_data else None,
            'estimate_change_rate': str(realtime_data.estimate_change_rate) if realtime_data and realtime_data.estimate_change_rate is not None else '-',
            'estimate_time': realtime_data.estimate_time if realtime_data else '',
            'one_month_rate': realtime_data.one_month_rate if realtime_data else 0,
            'three_month_rate': realtime_data.three_month_rate if realtime_data else 0,
            'one_year_rate': realtime_data.one_year_rate if realtime_data else 0,
            'daily_change_rate': realtime_data.daily_change_rate if realtime_data else 0,
            'fsrq': realtime_data.fsrq if realtime_data else '',
            'net_values': json.loads(realtime_data.net_values) if realtime_data and realtime_data.net_values else []
        }

# 辅助函数：计算持仓信息

def calculate_holding(fund_holding: FundHolding, current_price: float):
    """
    计算持仓的当前价值、盈亏等信息
    :param fund_holding: 持仓对象
    :param current_price: 当前基金净值
    :return: 更新后的持仓对象
    """
    fund_holding.current_value = fund_holding.shares * current_price
    # 持有收益 = 当前价值 - 持仓成本
    fund_holding.profit_loss = fund_holding.current_value - fund_holding.cost
    # 收益率 = 持有收益 / 持仓成本
    if fund_holding.cost > 0:
        fund_holding.profit_loss_rate = (fund_holding.profit_loss / fund_holding.cost) * 100
    else:
        fund_holding.profit_loss_rate = 0
    return fund_holding

# API接口

@app.route('/api/fund/search', methods=['GET'])
def search_fund():
    """
    搜索基金
    :return: 基金列表
    """
    keyword = request.args.get('keyword', '')
    if not keyword:
        return jsonify({'error': '关键词不能为空'}), 400

    funds = DataFetcher.search_fund(keyword)
    return jsonify(funds)

@app.route('/api/fund/<fund_code>', methods=['GET'])
def get_fund_detail(fund_code):
    """
    获取基金详情
    优先从数据库读取缓存数据，如果数据不是最新的再从API获取
    :param fund_code: 基金代码
    :return: 基金详情
    """
    from datetime import datetime, timedelta
    db = next(get_db())
    try:
        # 先尝试从数据库获取基金信息和缓存数据
        fund = db.query(Fund).filter(Fund.fund_code == fund_code).first()

        # 检查数据库中是否有有效的缓存数据
        use_cache = False
        if fund and fund.realtime_data:
            fsrq = fund.realtime_data.fsrq
            updated_at = fund.realtime_data.updated_at

            if fsrq and updated_at:
                now = now_cst_naive()
                today_str = now.strftime('%Y-%m-%d')

                # 如果fsrq是当日，说明数据是最新的，使用缓存
                if fsrq == today_str:
                    use_cache = True
                    print(f"基金 {fund_code} 使用数据库缓存数据，fsrq={fsrq}")

        if use_cache:
            # 使用数据库缓存的数据
            fund_data = {
                'fund_code': fund_code,
                'fund_name': fund.fund_name,
                'net_value': fund.realtime_data.net_value_date or '',
                'unit_net_value': fund.realtime_data.unit_net_value,
                'estimate_net_value': fund.realtime_data.estimate_net_value,
                'estimate_change_rate': str(fund.realtime_data.estimate_change_rate) if fund.realtime_data.estimate_change_rate is not None else '-',
                'estimate_time': fund.realtime_data.estimate_time or '',
                'one_month_rate': fund.realtime_data.one_month_rate or 0,
                'three_month_rate': fund.realtime_data.three_month_rate or 0,
                'one_year_rate': fund.realtime_data.one_year_rate or 0,
                'daily_change_rate': fund.realtime_data.daily_change_rate or 0,
                'fsrq': fund.realtime_data.fsrq or ''
            }
        else:
            # 缓存数据不是最新的，从API获取
            print(f"基金 {fund_code} 缓存数据不是最新，从API获取")
            try:
                fund_data = DataFetcher.get_fund_valuation(fund_code)
            except Exception as e:
                print(f"获取基金估值失败: {e}")
                fund_data = None

            try:
                history_data = DataFetcher.get_fund_history(fund_code)
            except Exception as e:
                print(f"获取基金历史数据失败: {e}")
                history_data = None

            # 即使估值数据不可用，只要有历史数据，就返回数据
            if not fund_data and not history_data:
                return jsonify({'error': '获取基金数据失败'}), 404

            # 如果估值数据不可用，使用基本结构
            if not fund_data:
                fund_data = {
                    'fund_code': fund_code,
                    'fund_name': fund.fund_name if fund else '',
                    'net_value': '',
                    'unit_net_value': None,
                    'estimate_net_value': None,
                    'estimate_change_rate': '-',
                    'estimate_time': ''
                }

            # 添加历史数据到fund_data
            if history_data:
                fund_data['one_month_rate'] = history_data.get('one_month_rate', 0)
                fund_data['three_month_rate'] = history_data.get('three_month_rate', 0)
                fund_data['one_year_rate'] = history_data.get('one_year_rate', 0)
                fund_data['daily_change_rate'] = history_data.get('daily_change_rate', 0)
                fund_data['fsrq'] = history_data.get('fsrq', '')

                # 更新数据库缓存（0值/空值不覆盖非0值，旧日期不覆盖新日期）
                if fund:
                    if not fund.realtime_data:
                        fund.realtime_data = FundRealtimeData(fund_id=fund.id)

                    new_fsrq = history_data.get('fsrq', '')
                    old_fsrq = fund.realtime_data.fsrq or ''

                    for field, key in [('one_month_rate', 'one_month_rate'), ('three_month_rate', 'three_month_rate'),
                                       ('one_year_rate', 'one_year_rate'), ('daily_change_rate', 'daily_change_rate'),
                                       ('unit_net_value', 'unit_net_value')]:
                        new_val = history_data.get(key, 0)
                        old_val = getattr(fund.realtime_data, field, None)
                        if (new_val == 0 or new_val is None) and old_val and old_val != 0:
                            continue
                        setattr(fund.realtime_data, field, new_val)
                    if new_fsrq:
                        fund.realtime_data.fsrq = new_fsrq
                    if fund_data:
                        est_rate = fund_data.get('estimate_change_rate')
                        # estimate_change_rate 是 double 类型，不能存入 '-' 字符串
                        if est_rate is not None and est_rate != '-':
                            try:
                                fund.realtime_data.estimate_change_rate = float(est_rate)
                            except (ValueError, TypeError):
                                pass
                        fund.realtime_data.estimate_time = fund_data.get('estimate_time', '')
                    fund.realtime_data.updated_at = datetime.now()
                    db.commit()

        # 获取基金重仓股数据（重仓股数据不缓存，每次实时获取）
        try:
            holdings = DataFetcher.get_fund_holding(fund_code)
            fund_data['holdings'] = holdings
        except Exception as e:
            print(f"获取基金重仓股失败: {e}")
            fund_data['holdings'] = []

        return jsonify(fund_data)
    finally:
        db.close()

@app.route('/api/fund/<fund_code>/history', methods=['GET'])
def get_fund_history(fund_code):
    """
    获取基金历史净值数据
    优先从数据库读取，如果没有或数据过期则从第三方接口获取
    :param fund_code: 基金代码
    :return: 历史净值数据和近1个月涨幅
    """
    from datetime import datetime, timedelta
    print(f"[DEBUG] 收到历史净值请求: fund_code={fund_code}")
    logger.info(f"收到历史净值请求: fund_code={fund_code}")

    force_refresh = request.args.get('force_refresh', 'false').lower() == 'true'
    db = next(get_db())
    try:
        fund = db.query(Fund).filter(Fund.fund_code == fund_code).first()

        if not force_refresh and fund and fund.realtime_data and fund.realtime_data.net_values:
            # 先解析缓存的历史净值数据
            cached_net_values = json.loads(fund.realtime_data.net_values) if fund.realtime_data.net_values else []

            # 如果缓存数据为空，跳过缓存，强制重新获取
            if not cached_net_values:
                print(f"[DEBUG] 基金 {fund_code} 缓存的历史净值数据为空，需要重新获取")
            else:
                updated_at = fund.realtime_data.updated_at
                fsrq = fund.realtime_data.fsrq or ''

                now = now_cst_naive()
                is_weekday = now.weekday() < 5

                data_is_fresh = False
                if updated_at and (now - updated_at.replace(tzinfo=None)) < timedelta(hours=6):
                    # 如果fsrq是周末，数据一定有问题（基金净值不可能在非交易日确认），强制刷新
                    fsrq_is_weekend = False
                    if fsrq:
                        try:
                            fsrq_date = datetime.strptime(fsrq, '%Y-%m-%d')
                            if fsrq_date.weekday() >= 5:
                                print(f"[DEBUG] 基金 {fund_code} fsrq({fsrq})是周末，缓存数据有误，需要重新获取")
                                fsrq_is_weekend = True
                        except ValueError:
                            pass

                    if not fsrq_is_weekend:
                        # 检查net_values最新日期是否与fsrq一致
                        cached_latest_date = cached_net_values[0].get('date', '') if cached_net_values else ''
                        if fsrq and cached_latest_date == fsrq:
                            today_str = now.strftime('%Y-%m-%d')
                            if now.weekday() == 0:
                                expected_dates = [today_str, (now - timedelta(days=3)).strftime('%Y-%m-%d')]
                            elif now.hour < 18 and is_weekday:
                                expected_dates = [(now - timedelta(days=1)).strftime('%Y-%m-%d'), today_str]
                            else:
                                expected_dates = [today_str, (now - timedelta(days=1)).strftime('%Y-%m-%d')]

                            if fsrq in expected_dates:
                                data_is_fresh = True
                        elif not fsrq:
                            data_is_fresh = False
                        else:
                            print(f"[DEBUG] 基金 {fund_code} net_values最新日期({cached_latest_date})与fsrq({fsrq})不一致，需要重新获取")

                if data_is_fresh:
                    return jsonify({
                        'fund_code': fund_code,
                        'net_values': cached_net_values,
                        'one_month_rate': fund.realtime_data.one_month_rate or 0,
                        'three_month_rate': fund.realtime_data.three_month_rate or 0,
                        'one_year_rate': fund.realtime_data.one_year_rate or 0,
                        'daily_change_rate': fund.realtime_data.daily_change_rate or 0,
                        'fsrq': fund.realtime_data.fsrq or '',
                        'unit_net_value': fund.realtime_data.unit_net_value or 0
                    })

        history_data = DataFetcher.get_fund_history(fund_code, int(time.time()))

        # 检查获取的数据是否有效（包含历史净值或涨跌幅数据）
        has_valid_net_values = history_data.get('net_values') and len(history_data.get('net_values', [])) > 0
        has_valid_rates = any([
            history_data.get('one_month_rate', 0) != 0,
            history_data.get('three_month_rate', 0) != 0,
            history_data.get('one_year_rate', 0) != 0,
            history_data.get('daily_change_rate', 0) != 0,
            history_data.get('unit_net_value', 0) != 0
        ])

        # 如果获取的数据无效，返回数据库中的现有数据而不更新
        if not has_valid_net_values and not has_valid_rates:
            print(f"[DEBUG] 基金 {fund_code} 从第三方接口获取数据无效，使用数据库缓存")
            if fund and fund.realtime_data and fund.realtime_data.net_values:
                cached_net_values = json.loads(fund.realtime_data.net_values) if fund.realtime_data.net_values else []
                return jsonify({
                    'fund_code': fund_code,
                    'net_values': cached_net_values,
                    'one_month_rate': fund.realtime_data.one_month_rate or 0,
                    'three_month_rate': fund.realtime_data.three_month_rate or 0,
                    'one_year_rate': fund.realtime_data.one_year_rate or 0,
                    'daily_change_rate': fund.realtime_data.daily_change_rate or 0,
                    'fsrq': fund.realtime_data.fsrq or '',
                    'unit_net_value': fund.realtime_data.unit_net_value or 0
                })

        # 数据有效，更新数据库
        if fund:
            if not fund.realtime_data:
                fund.realtime_data = FundRealtimeData(fund_id=fund.id)

            # 只有当获取到有效数据时才更新 net_values
            if has_valid_net_values:
                fund.realtime_data.net_values = json.dumps(history_data.get('net_values', []))
            # 涨跌幅数据如果有效则更新
            if has_valid_rates:
                fund.realtime_data.one_month_rate = history_data.get('one_month_rate', 0)
                fund.realtime_data.three_month_rate = history_data.get('three_month_rate', 0)
                fund.realtime_data.one_year_rate = history_data.get('one_year_rate', 0)
                fund.realtime_data.daily_change_rate = history_data.get('daily_change_rate', 0)
                fund.realtime_data.fsrq = history_data.get('fsrq', '')
                fund.realtime_data.unit_net_value = history_data.get('unit_net_value', 0)

            fund.realtime_data.updated_at = datetime.now()
            db.commit()

        return jsonify(history_data)
    except Exception as e:
        logger.error(f"获取基金历史净值失败: {e}")
        if fund and fund.realtime_data and fund.realtime_data.net_values:
            net_values = json.loads(fund.realtime_data.net_values) if fund.realtime_data.net_values else []
            return jsonify({
                'fund_code': fund_code,
                'net_values': net_values,
                'one_month_rate': fund.realtime_data.one_month_rate or 0,
                'three_month_rate': fund.realtime_data.three_month_rate or 0,
                'one_year_rate': fund.realtime_data.one_year_rate or 0,
                'daily_change_rate': fund.realtime_data.daily_change_rate or 0,
                'fsrq': fund.realtime_data.fsrq or '',
                'unit_net_value': fund.realtime_data.unit_net_value or 0
            })
        return jsonify({'error': str(e)}), 500
    finally:
        db.close()

@app.route('/api/fund/preload-history', methods=['POST'])
@jwt_required()
def trigger_preload_history():
    try:
        # 在后台线程中执行预加载，避免阻塞请求
        def run_preload():
            preload_all_funds_history()

        thread = threading.Thread(target=run_preload)
        thread.daemon = True
        thread.start()

        return jsonify({
            'success': True,
            'message': '历史净值预加载任务已启动，请在后台查看进度'
        })
    except Exception as e:
        logger.error(f"启动预加载任务失败: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/fund/<fund_code>/complete', methods=['GET'])
@jwt_required(optional=True)
def get_fund_complete_info(fund_code):
    """
    获取基金完整信息，包括基本信息、历史净值和交易记录
    :param fund_code: 基金代码
    :return: 基金完整信息
    """
    from datetime import datetime, timedelta
    from flask_jwt_extended import get_jwt_identity
    db = next(get_db())
    try:
        # 获取当前用户ID（可选，未登录时返回None）
        user_id = get_jwt_identity()
        # 并行获取数据
        from concurrent.futures import ThreadPoolExecutor

        def get_basic_info():
            """获取基金基本信息"""
            fund = db.query(Fund).filter(Fund.fund_code == fund_code).first()
            if fund:
                # 从Watchlist表中获取标签信息
                watchlist = db.query(Watchlist).filter(Watchlist.fund_id == fund.id).first()
                tags = watchlist.tags if watchlist else ''
                return {
                    'fund_code': fund.fund_code,
                    'fund_name': fund.fund_name,
                    'tags': tags
                }
            return None

        def get_history_data():
            """获取基金历史净值"""
            # 先尝试从数据库获取
            fund = db.query(Fund).filter(Fund.fund_code == fund_code).first()
            if fund and fund.realtime_data and fund.realtime_data.net_values:
                # 检查数据是否过期（超过1天）
                updated_at = fund.realtime_data.updated_at
                net_values = json.loads(fund.realtime_data.net_values) if fund.realtime_data.net_values else []

                # 检查数据是否过期或者 net_values 为空数组
                data_is_valid = (
                    updated_at and
                    (datetime.now() - updated_at.replace(tzinfo=None)) < timedelta(days=1) and
                    len(net_values) > 0
                )

                if data_is_valid:
                    # 数据未过期且 net_values 不为空，直接返回数据库中的数据
                    return {
                        'fund_code': fund_code,
                        'net_values': net_values,
                        'one_month_rate': fund.realtime_data.one_month_rate or 0,
                        'three_month_rate': fund.realtime_data.three_month_rate or 0,
                        'one_year_rate': fund.realtime_data.one_year_rate or 0,
                        'daily_change_rate': fund.realtime_data.daily_change_rate or 0,
                        'fsrq': fund.realtime_data.fsrq or '',
                        'unit_net_value': fund.realtime_data.unit_net_value or 0,
                        'estimate_change_rate': str(fund.realtime_data.estimate_change_rate) if fund.realtime_data.estimate_change_rate is not None else '-',
                        'estimate_time': fund.realtime_data.estimate_time or ''
                    }

            # 数据不存在、已过期或 net_values 为空，从第三方接口获取
            logger.info(f"从第三方接口获取基金 {fund_code} 的历史数据")
            history_data = DataFetcher.get_fund_history(fund_code)
            logger.info(f"从第三方获取到的历史数据中 net_values 数量: {len(history_data.get('net_values', []))}")

            # 获取估值数据
            estimate_data = DataFetcher._get_fund_valuation_no_retry(fund_code)

            # 保存到数据库
            if fund:
                if not fund.realtime_data:
                    fund.realtime_data = FundRealtimeData(fund_id=fund.id)
                fund.realtime_data.net_values = json.dumps(history_data.get('net_values', []))

                # 涨跌幅数据：0值/空值不覆盖数据库中的非0/非空值，旧日期不覆盖新日期
                new_fsrq = history_data.get('fsrq', '')
                old_fsrq = fund.realtime_data.fsrq or ''

                for field, key in [('one_month_rate', 'one_month_rate'), ('three_month_rate', 'three_month_rate'),
                                   ('one_year_rate', 'one_year_rate'), ('daily_change_rate', 'daily_change_rate'),
                                   ('unit_net_value', 'unit_net_value')]:
                    new_val = history_data.get(key, 0)
                    old_val = getattr(fund.realtime_data, field, None)
                    if (new_val == 0 or new_val is None) and old_val and old_val != 0:
                        continue
                    setattr(fund.realtime_data, field, new_val)

                if new_fsrq:
                    fund.realtime_data.fsrq = new_fsrq
                # 更新估值数据
                if estimate_data:
                    fund.realtime_data.estimate_change_rate = float(estimate_data.get('estimate_change_rate')) if estimate_data.get('estimate_change_rate') else None
                    fund.realtime_data.estimate_time = estimate_data.get('estimate_time', '')
                fund.realtime_data.updated_at = datetime.now()
                db.commit()
                logger.info(f"已保存基金 {fund_code} 的历史数据到数据库，net_values 数量: {len(history_data.get('net_values', []))}")

            # 添加估值数据到返回结果
            history_data['estimate_change_rate'] = str(estimate_data.get('estimate_change_rate')) if estimate_data and estimate_data.get('estimate_change_rate') else '-'
            history_data['estimate_time'] = estimate_data.get('estimate_time', '') if estimate_data else ''

            return history_data

        def get_transactions():
            """获取基金交易记录"""
            # 先获取基金ID
            fund = db.query(Fund).filter(Fund.fund_code == fund_code).first()
            if not fund:
                return []

            # 通过fund_id查询交易记录
            query = db.query(Transaction).filter(Transaction.fund_id == fund.id)
            if user_id:
                query = query.filter(Transaction.user_id == user_id)
            transactions = query.order_by(Transaction.transaction_date.desc()).all()

            return [{
                'id': t.id,
                'fund_code': fund_code,
                'type': t.transaction_type,
                'amount': t.amount,
                'shares': t.shares,
                'price': t.price,
                'date': t.transaction_date.strftime('%Y-%m-%d %H:%M:%S'),
                'platform_id': t.platform_id  # 返回平台ID
            } for t in transactions]

        # 串行执行（避免SQLAlchemy session线程安全问题）
        basic_info = get_basic_info()
        history_data = get_history_data()
        transactions = get_transactions()

        # 构建响应
        response = {
            'fund_info': basic_info,
            'history_data': history_data,
            'transactions': transactions
        }

        return jsonify(response)
    except Exception as e:
        logger.error(f"获取基金完整信息失败: {e}")
        return jsonify({'error': str(e)}), 500
    finally:
        db.close()

@app.route('/api/fund/add', methods=['POST'])
def add_fund():
    """
    添加基金
    :return: 添加结果
    """
    data = request.json
    fund_code = data.get('fund_code')
    if not fund_code:
        return jsonify({'error': '基金代码不能为空'}), 400

    db = next(get_db())
    try:
        fund = get_or_create_fund(db, fund_code)
        return jsonify({'success': True, 'fund': {'id': fund.id, 'fund_code': fund.fund_code, 'fund_name': fund.fund_name}})
    except Exception as e:
        db.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        db.close()

def _get_public_watchlist(db):
    from datetime import datetime

    fund_codes = DEFAULT_PUBLIC_FUNDS
    if not fund_codes:
        return jsonify([])

    for fund_code in fund_codes:
        fund_code = fund_code.strip()
        if not fund_code:
            continue
        existing = db.query(Fund).filter(Fund.fund_code == fund_code).first()
        if not existing:
            new_fund = Fund(
                fund_code=fund_code,
                fund_name=fund_code
            )
            db.add(new_fund)
    db.commit()

    now = now_cst_naive()
    is_trading_day = now.weekday() < 5

    # 数据库优先策略：先从数据库读取缓存数据
    funds_data_dict = {}
    for fund_code in fund_codes:
        fund_code = fund_code.strip()
        if not fund_code:
            continue
        fund = db.query(Fund).filter(Fund.fund_code == fund_code).first()
        if fund:
            realtime_data = db.query(FundRealtimeData).filter(
                FundRealtimeData.fund_id == fund.id
            ).first()
            if realtime_data:
                funds_data_dict[fund_code] = {
                    'fund_code': fund_code,
                    'fund_name': fund.fund_name,
                    'net_value': realtime_data.fsrq or realtime_data.net_value_date,
                    'unit_net_value': realtime_data.unit_net_value,
                    'estimate_net_value': realtime_data.estimate_net_value,
                    'estimate_change_rate': str(realtime_data.estimate_change_rate) if realtime_data.estimate_change_rate is not None else '-',
                    'estimate_time': realtime_data.estimate_time,
                    'one_month_rate': realtime_data.one_month_rate,
                    'three_month_rate': realtime_data.three_month_rate,
                    'one_year_rate': realtime_data.one_year_rate,
                    'daily_change_rate': realtime_data.daily_change_rate,
                    'fsrq': realtime_data.fsrq,
                    'net_values': []
                }

    all_cached = len(funds_data_dict) >= len(set([c.strip() for c in fund_codes if c.strip()]))

    has_stale_estimate_public = False
    now_pub = now_cst_naive()
    today_str_pub = now_pub.strftime('%Y-%m-%d')
    is_trading_hours_pub = now_pub.weekday() < 5 and now_pub.hour >= 9 and now_pub.hour < 15
    if is_trading_hours_pub:
        for fc, fd in funds_data_dict.items():
            fd_etime = fd.get('estimate_time', '') or ''
            fd_ecr = fd.get('estimate_change_rate', '-')
            if fd_ecr == '-' or fd_ecr is None or not fd_etime.startswith(today_str_pub):
                has_stale_estimate_public = True
                break

    try:
        executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        future = executor.submit(get_fund_realtime_rates_batch, db, [c.strip() for c in fund_codes if c.strip()], False)
        if all_cached and not has_stale_estimate_public:
            executor.shutdown(wait=False)
        else:
            try:
                fresh_data = future.result(timeout=60)
                if fresh_data:
                    _merge_fund_data(funds_data_dict, fresh_data)
            except concurrent.futures.TimeoutError:
                pass
            executor.shutdown(wait=False)
    except Exception as e:
        logger.error(f"公共watchlist批量获取基金实时数据失败: {e}")
    funds = []
    for fund_code in fund_codes:
        fund_code = fund_code.strip()
        if not fund_code:
            continue
        fund_data = funds_data_dict.get(fund_code)

        # 检查数据是否有效（不为空且至少有一个非零值）
        has_valid_data = fund_data and any([
            fund_data.get('estimate_change_rate') is not None,
            fund_data.get('daily_change_rate') is not None and fund_data.get('daily_change_rate') != '-',
            fund_data.get('one_month_rate', 0) != 0,
            fund_data.get('three_month_rate', 0) != 0,
            fund_data.get('one_year_rate', 0) != 0,
            fund_data.get('unit_net_value') is not None and fund_data.get('unit_net_value') != ''
        ])

        if has_valid_data:
            fund_data['tags'] = ''
            if not is_trading_day:
                fund_data['estimate_change_rate'] = '-'
            funds.append(fund_data)
        else:
            # 从数据库缓存中获取数据
            fund = db.query(Fund).filter(Fund.fund_code == fund_code).first()
            if fund and fund.realtime_data:
                rt = fund.realtime_data
                funds.append({
                    'fund_code': fund_code,
                    'fund_name': fund.fund_name,
                    'net_value': rt.fsrq or rt.net_value_date or '',
                    'unit_net_value': rt.unit_net_value or '',
                    'estimate_net_value': rt.estimate_net_value or '',
                    'estimate_change_rate': str(rt.estimate_change_rate) if rt.estimate_change_rate is not None else '-',
                    'estimate_time': rt.estimate_time or '',
                    'one_month_rate': rt.one_month_rate or 0,
                    'three_month_rate': rt.three_month_rate or 0,
                    'one_year_rate': rt.one_year_rate or 0,
                    'daily_change_rate': rt.daily_change_rate or '-',
                    'tags': ''
                })
            else:
                funds.append({
                    'fund_code': fund_code,
                    'fund_name': fund.fund_name if fund else fund_code,
                    'net_value': '',
                    'unit_net_value': '',
                    'estimate_net_value': '',
                    'estimate_change_rate': '-',
                    'estimate_time': '',
                    'one_month_rate': 0,
                    'three_month_rate': 0,
                    'one_year_rate': 0,
                    'daily_change_rate': '-',
                    'tags': ''
                })
    return jsonify(funds)

@app.route('/api/watchlist', methods=['GET', 'POST', 'DELETE'])
@jwt_required(optional=True)
def manage_watchlist():
    from datetime import datetime
    db = next(get_db())
    try:
        user_id = get_current_user_id()

        if request.method == 'GET':
            if not user_id:
                return _get_public_watchlist(db)

            watchlist = db.query(Watchlist).filter(Watchlist.user_id == user_id).all()
            funds = []

            # 收集所有自选基金的fund_code
            watchlist_fund_codes = []
            watchlist_fund_ids = set()

            for item in watchlist:
                if item.fund:
                    watchlist_fund_codes.append(item.fund.fund_code)
                    watchlist_fund_ids.add(item.fund.id)

            # 判断是否是交易日（周一到周五）
            now = now_cst_naive()
            is_trading_day = now.weekday() < 5

            # 数据库优先策略：先从数据库读取缓存数据
            funds_data_dict = {}
            for item in watchlist:
                if item.fund:
                    realtime_data = db.query(FundRealtimeData).filter(
                        FundRealtimeData.fund_id == item.fund.id
                    ).first()
                    if realtime_data:
                        funds_data_dict[item.fund.fund_code] = {
                            'fund_code': item.fund.fund_code,
                            'fund_name': item.fund.fund_name,
                            'net_value': realtime_data.fsrq or realtime_data.net_value_date,
                            'unit_net_value': realtime_data.unit_net_value,
                            'estimate_net_value': realtime_data.estimate_net_value,
                            'estimate_change_rate': str(realtime_data.estimate_change_rate) if realtime_data.estimate_change_rate is not None else '-',
                            'estimate_time': realtime_data.estimate_time,
                            'one_month_rate': realtime_data.one_month_rate,
                            'three_month_rate': realtime_data.three_month_rate,
                            'one_year_rate': realtime_data.one_year_rate,
                            'daily_change_rate': realtime_data.daily_change_rate,
                            'fsrq': realtime_data.fsrq,
                            'net_values': []
                        }

            all_cached = len(funds_data_dict) >= len(set(watchlist_fund_codes))

            has_stale_estimate = False
            now_wl = now_cst_naive()
            today_str_wl = now_wl.strftime('%Y-%m-%d')
            is_trading_hours_wl = now_wl.weekday() < 5 and now_wl.hour >= 9 and now_wl.hour < 15
            if is_trading_hours_wl:
                for fc, fd in funds_data_dict.items():
                    fd_etime = fd.get('estimate_time', '') or ''
                    fd_ecr = fd.get('estimate_change_rate', '-')
                    if fd_ecr == '-' or fd_ecr is None or not fd_etime.startswith(today_str_wl):
                        has_stale_estimate = True
                        break

            try:
                executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
                future = executor.submit(get_fund_realtime_rates_batch, db, watchlist_fund_codes, False)
                if all_cached and not has_stale_estimate:
                    executor.shutdown(wait=False)
                else:
                    try:
                        fresh_data = future.result(timeout=60)
                        if fresh_data:
                            _merge_fund_data(funds_data_dict, fresh_data)
                    except concurrent.futures.TimeoutError:
                        pass
                    executor.shutdown(wait=False)
            except Exception as e:
                logger.error(f"watchlist批量获取基金实时数据失败: {e}")

            today = now_cst_naive().strftime('%Y-%m-%d')

            for item in watchlist:
                if not item.fund:
                    continue

                fund_code = item.fund.fund_code
                fund_data = funds_data_dict.get(fund_code)

                if fund_data:
                    fund_data['tags'] = item.tags
                    # 非交易日（周末），估算涨幅显示为"-"
                    if not is_trading_day:
                        fund_data['estimate_change_rate'] = '-'
                    funds.append(fund_data)
                else:
                    # 即使数据获取失败，也要返回基本信息
                    basic_fund_data = {
                        'fund_code': fund_code,
                        'fund_name': item.fund.fund_name,
                        'net_value': '',
                        'unit_net_value': '',
                        'estimate_net_value': '',
                        'estimate_change_rate': None,
                        'estimate_time': '',
                        'one_month_rate': 0,
                        'three_month_rate': 0,
                        'one_year_rate': 0,
                        'daily_change_rate': '-',
                        'tags': item.tags
                    }
                    funds.append(basic_fund_data)

            holdings = db.query(FundHolding).filter(FundHolding.user_id == user_id).all()
            holding_fund_codes = []

            for holding in holdings:
                if holding.fund.id not in watchlist_fund_ids:
                    holding_fund_codes.append(holding.fund.fund_code)

            # 去重持仓基金代码
            holding_fund_codes = list(set(holding_fund_codes))

            # 如果有持仓基金需要获取数据，使用数据库优先策略
            if holding_fund_codes:
                # 先从数据库读取缓存
                holding_funds_data_dict = {}
                for holding in holdings:
                    if holding.fund.id in watchlist_fund_ids:
                        continue
                    if holding.fund.fund_code in holding_funds_data_dict:
                        continue
                    realtime_data = db.query(FundRealtimeData).filter(
                        FundRealtimeData.fund_id == holding.fund.id
                    ).first()
                    if realtime_data:
                        holding_funds_data_dict[holding.fund.fund_code] = {
                            'fund_code': holding.fund.fund_code,
                            'fund_name': holding.fund.fund_name,
                            'net_value': realtime_data.fsrq or realtime_data.net_value_date,
                            'unit_net_value': realtime_data.unit_net_value,
                            'estimate_net_value': realtime_data.estimate_net_value,
                            'estimate_change_rate': str(realtime_data.estimate_change_rate) if realtime_data.estimate_change_rate is not None else '-',
                            'estimate_time': realtime_data.estimate_time,
                            'one_month_rate': realtime_data.one_month_rate,
                            'three_month_rate': realtime_data.three_month_rate,
                            'one_year_rate': realtime_data.one_year_rate,
                            'daily_change_rate': realtime_data.daily_change_rate,
                            'fsrq': realtime_data.fsrq,
                            'net_values': []
                        }

                all_holding_cached = len(holding_funds_data_dict) >= len(set(holding_fund_codes))

                has_stale_holding_estimate = False
                if is_trading_hours_wl:
                    for fc, fd in holding_funds_data_dict.items():
                        fd_etime = fd.get('estimate_time', '') or ''
                        fd_ecr = fd.get('estimate_change_rate', '-')
                        if fd_ecr == '-' or fd_ecr is None or not fd_etime.startswith(today_str_wl):
                            has_stale_holding_estimate = True
                            break

                try:
                    executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
                    future = executor.submit(get_fund_realtime_rates_batch, db, holding_fund_codes, False)
                    if all_holding_cached and not has_stale_holding_estimate:
                        executor.shutdown(wait=False)
                    else:
                        try:
                            fresh_data = future.result(timeout=8)
                            if fresh_data:
                                _merge_fund_data(holding_funds_data_dict, fresh_data)
                        except concurrent.futures.TimeoutError:
                            pass
                        executor.shutdown(wait=False)
                except Exception as e:
                    logger.error(f"watchlist持仓基金批量获取数据失败: {e}")

                # 构建持仓基金返回结果
                added_fund_codes = set()
                for holding in holdings:
                    if holding.fund.id in watchlist_fund_ids:
                        continue

                    fund_code = holding.fund.fund_code

                    # 检查是否已经添加过该基金
                    if fund_code in added_fund_codes:
                        continue

                    fund_data = holding_funds_data_dict.get(fund_code)

                    if fund_data:
                        fund_data['tags'] = ''
                        # 非交易日（周末），估算涨幅显示为"-"
                        if not is_trading_day:
                            fund_data['estimate_change_rate'] = '-'
                        funds.append(fund_data)
                        added_fund_codes.add(fund_code)
                    else:
                        basic_fund_data = {
                            'fund_code': fund_code,
                            'fund_name': holding.fund.fund_name,
                            'net_value': '',
                            'unit_net_value': '',
                            'estimate_net_value': '',
                            'estimate_change_rate': None,
                            'estimate_time': '',
                            'one_month_rate': 0,
                            'three_month_rate': 0,
                            'one_year_rate': 0,
                            'daily_change_rate': '-',
                            'tags': ''
                        }
                        funds.append(basic_fund_data)
                        added_fund_codes.add(fund_code)

            return jsonify(funds)

        elif request.method == 'POST':
            if not user_id:
                return jsonify({'error': '请先登录'}), 401

            data = request.json
            fund_code = data.get('fund_code')
            if not fund_code:
                return jsonify({'error': '基金代码不能为空'}), 400

            fund = get_or_create_fund(db, fund_code)
            if not fund:
                return jsonify({'error': '获取基金信息失败，请稍后重试'}), 400
            existing = db.query(Watchlist).filter(Watchlist.fund_id == fund.id, Watchlist.user_id == user_id).first()
            if existing:
                return jsonify({'error': '该基金已在自选列表中'}), 400

            tags = data.get('tags', '')
            watchlist_item = Watchlist(fund_id=fund.id, user_id=user_id, tags=tags)
            db.add(watchlist_item)
            db.commit()

            # 获取完整的基金数据
            fund_data = get_fund_realtime_rates(db, fund_code)
            if fund_data:
                fund_data['tags'] = tags
            else:
                fund_data = {
                    'fund_code': fund_code,
                    'fund_name': fund.fund_name,
                    'tags': tags,
                    'net_value': '',
                    'unit_net_value': '',
                    'estimate_net_value': '',
                    'estimate_change_rate': '-',
                    'estimate_time': '',
                    'one_month_rate': 0,
                    'three_month_rate': 0,
                    'one_year_rate': 0,
                    'daily_change_rate': '-',
                    'fsrq': ''
                }

            return jsonify({'success': True, 'fund': fund_data})

        elif request.method == 'DELETE':
            if not user_id:
                return jsonify({'error': '请先登录'}), 401

            data = request.json
            fund_code = data.get('fund_code')
            if not fund_code:
                return jsonify({'error': '基金代码不能为空'}), 400

            fund = db.query(Fund).filter(Fund.fund_code == fund_code).first()
            if fund:
                watchlist_item = db.query(Watchlist).filter(Watchlist.fund_id == fund.id, Watchlist.user_id == user_id).first()
                if watchlist_item:
                    db.delete(watchlist_item)
                    db.commit()
            return jsonify({'success': True})
    except Exception as e:
        import traceback
        error_message = str(e)
        error_traceback = traceback.format_exc()
        print(f"[ERROR] 处理 /api/watchlist 请求时出错: {error_message}")
        print(f"[ERROR] 详细错误信息: {error_traceback}")
        db.rollback()
        return jsonify({'error': error_message}), 500
    finally:
        db.close()

@app.route('/api/holding', methods=['GET', 'POST'])
@jwt_required()
def manage_holding():
    from datetime import datetime, timedelta
    try:
        logger.info("开始处理 /api/holding 请求")
        user_id = get_current_user_id()
        logger.info("获取数据库连接")
        db = next(get_db())
        logger.info("数据库连接获取成功")

        if request.method == 'GET':
            logger.info("处理 GET 请求")

            logger.info("开始获取持仓列表")
            try:
                holdings = db.query(FundHolding).filter(FundHolding.user_id == user_id).all()
                logger.info(f"获取到 {len(holdings)} 个持仓")
            except Exception as e:
                logger.error(f"获取持仓列表失败: {e}")
                return jsonify({'error': '获取持仓列表失败'}), 500

            # 批量获取所有基金的实时数据（使用与自选基金相同的批量方法）
            # 过滤掉 fund 为 None 的持仓
            valid_holdings = [h for h in holdings if h.fund is not None]
            if len(valid_holdings) != len(holdings):
                logger.warning(f"过滤掉 {len(holdings) - len(valid_holdings)} 个无效持仓（fund 为 None）")
            holdings = valid_holdings

            fund_codes = [holding.fund.fund_code for holding in holdings]
            logger.info(f"基金代码: {fund_codes}")

            fund_data_dict = {}

            for holding in holdings:
                if holding.fund:
                    realtime_data = db.query(FundRealtimeData).filter(
                        FundRealtimeData.fund_id == holding.fund.id
                    ).first()
                    if realtime_data:
                        fund_data_dict[holding.fund.fund_code] = {
                            'fund_code': holding.fund.fund_code,
                            'fund_name': holding.fund.fund_name,
                            'net_value': realtime_data.fsrq or realtime_data.net_value_date,
                            'unit_net_value': realtime_data.unit_net_value,
                            'estimate_net_value': realtime_data.estimate_net_value,
                            'estimate_change_rate': str(realtime_data.estimate_change_rate) if realtime_data.estimate_change_rate is not None else '-',
                            'estimate_time': realtime_data.estimate_time,
                            'one_month_rate': realtime_data.one_month_rate,
                            'three_month_rate': realtime_data.three_month_rate,
                            'one_year_rate': realtime_data.one_year_rate,
                            'daily_change_rate': realtime_data.daily_change_rate,
                            'fsrq': realtime_data.fsrq,
                            'net_values': []
                        }

            logger.info(f"数据库缓存命中 {len(fund_data_dict)}/{len(fund_codes)} 个基金")

            all_cached = len(fund_data_dict) >= len(set(fund_codes))

            has_stale_data = False
            has_stale_estimate = False
            now_check = now_cst_naive()
            today_str = now_check.strftime('%Y-%m-%d')
            if now_check.weekday() == 0:
                yesterday_str = (now_check - timedelta(days=3)).strftime('%Y-%m-%d')
            else:
                yesterday_str = (now_check - timedelta(days=1)).strftime('%Y-%m-%d')
            is_trading_hours = now_check.weekday() < 5 and now_check.hour >= 9 and now_check.hour < 15
            for fc, fd in fund_data_dict.items():
                fd_fsrq = fd.get('fsrq', '')
                if fd_fsrq and fd_fsrq != today_str and fd_fsrq != yesterday_str:
                    has_stale_data = True
                    break
                if is_trading_hours:
                    fd_etime = fd.get('estimate_time', '') or ''
                    fd_ecr = fd.get('estimate_change_rate', '-')
                    if fd_ecr == '-' or fd_ecr is None or not fd_etime.startswith(today_str):
                        has_stale_estimate = True
                        break

            try:
                executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
                future = executor.submit(get_fund_realtime_rates_batch, db, fund_codes, False)
                if all_cached and not has_stale_data and not has_stale_estimate:
                    executor.shutdown(wait=False)
                    logger.info("所有基金已有缓存且数据未过期，后台异步刷新")
                else:
                    try:
                        fresh_data = future.result(timeout=60)
                        if fresh_data:
                            _merge_fund_data(fund_data_dict, fresh_data)
                            logger.info(f"刷新数据完成，更新了 {len(fresh_data)} 个基金")
                    except concurrent.futures.TimeoutError:
                        logger.warning("批量获取基金实时数据超时(8秒)，使用数据库缓存数据")
                    executor.shutdown(wait=False)
            except Exception as e:
                logger.error(f"批量获取基金实时数据失败，使用数据库缓存: {e}")

            logger.info(f"获取到的基金数据: {fund_data_dict}")

            # 批量获取所有基金的标签（板块）
            fund_ids = [holding.fund.id for holding in holdings]
            watchlist_items = db.query(Watchlist).filter(Watchlist.fund_id.in_(fund_ids), Watchlist.user_id == user_id).all()
            tags_dict = {item.fund_id: item.tags for item in watchlist_items}

            holding_list = []
            # 判断是否是交易日（周一到周五）
            now = now_cst_naive()
            is_trading_day = now.weekday() < 5

            try:
                for holding in holdings:
                    # 检查持仓关联的基金是否存在
                    if not holding.fund:
                        logger.warning(f"持仓 {holding.id} 关联的基金不存在，跳过")
                        continue

                    fund_data = fund_data_dict.get(holding.fund.fund_code)
                    tags = tags_dict.get(holding.fund.id, '')

                    if fund_data:
                        unit_net_value = fund_data.get('unit_net_value')
                        fsrq = fund_data.get('fsrq', '')
                        daily_change_rate = fund_data.get('daily_change_rate', '-')
                        estimate_change_rate = fund_data.get('estimate_change_rate', '-')

                        today = now_cst_naive().strftime('%Y-%m-%d')
                        is_today = (fsrq == today)

                        if unit_net_value:
                            current_value = holding.shares * float(unit_net_value)
                        else:
                            current_value = holding.current_value or holding.cost
                        profit_loss = current_value - holding.cost
                        profit_loss_rate = (profit_loss / holding.cost * 100) if holding.cost > 0 else 0

                        if not is_trading_day:
                            estimate_change_rate = '-'
                            estimate_profit = None
                        elif unit_net_value:
                            estimate_time = fund_data.get('estimate_time', '')
                            estimate_is_today = False
                            if estimate_time:
                                estimate_date = estimate_time.split(' ')[0] if ' ' in estimate_time else estimate_time
                                estimate_is_today = (estimate_date == today)

                            # 优先使用估算涨幅计算今日收益
                            if estimate_is_today and estimate_change_rate not in ('-', None, '0', 0):
                                try:
                                    change_rate = float(estimate_change_rate)
                                    if change_rate != 0:
                                        estimate_profit = current_value * (change_rate / 100)
                                    else:
                                        estimate_profit = None
                                except (ValueError, TypeError):
                                    estimate_profit = None
                            elif is_today and daily_change_rate not in ('-', None, '0', 0):
                                try:
                                    change_rate = float(daily_change_rate)
                                    if change_rate != 0:
                                        estimate_profit = current_value * (change_rate / 100)
                                    else:
                                        estimate_profit = None
                                except (ValueError, TypeError):
                                    estimate_profit = None
                            else:
                                estimate_profit = None
                                if not estimate_is_today:
                                    estimate_change_rate = '-'
                        else:
                            estimate_profit = 0

                        holding_list.append({
                            'fund_code': holding.fund.fund_code,
                            'fund_name': holding.fund.fund_name,
                            'cost': holding.cost,
                            'shares': holding.shares,
                            'avg_cost': holding.avg_cost,
                            'current_value': current_value,
                            'profit_loss': profit_loss,
                            'profit_loss_rate': profit_loss_rate,
                            'estimate_change_rate': estimate_change_rate,
                            'estimate_profit': estimate_profit,
                            'estimate_time': fund_data.get('estimate_time', ''),
                            'daily_change_rate': fund_data.get('daily_change_rate', '-'),
                            'fsrq': fund_data.get('fsrq', ''),
                            'one_month_rate': fund_data.get('one_month_rate', 0),
                            'tags': tags,
                            'platform': holding.platform or '默认'
                        })
                    else:
                        # 降级策略：优先使用数据库中的实时数据，其次使用存储的旧值，最后使用成本价
                        realtime_data = db.query(FundRealtimeData).filter(
                            FundRealtimeData.fund_id == holding.fund.id
                        ).first()

                        current_value = holding.current_value
                        profit_loss = holding.profit_loss
                        profit_loss_rate = holding.profit_loss_rate
                        daily_change_rate = '-'
                        fsrq = ''
                        one_month_rate = 0
                        estimate_change_rate = '-'
                        estimate_profit = None

                        # 如果数据库中有实时数据，尝试使用它来计算
                        if realtime_data:
                            fsrq = realtime_data.fsrq or ''
                            one_month_rate = realtime_data.one_month_rate or 0
                            daily_change_rate = realtime_data.daily_change_rate or '-'

                            if realtime_data.unit_net_value:
                                try:
                                    current_value = holding.shares * float(realtime_data.unit_net_value)
                                    profit_loss = current_value - holding.cost
                                    profit_loss_rate = (profit_loss / holding.cost * 100) if holding.cost > 0 else 0
                                except (ValueError, TypeError):
                                    pass

                        # 最终降级到成本价
                        if current_value is None or current_value == 0:
                            current_value = holding.cost
                        if profit_loss is None:
                            profit_loss = 0
                        if profit_loss_rate is None:
                            profit_loss_rate = 0

                        holding_list.append({
                            'fund_code': holding.fund.fund_code,
                            'fund_name': holding.fund.fund_name,
                            'cost': holding.cost,
                            'shares': holding.shares,
                            'avg_cost': holding.avg_cost,
                            'current_value': current_value,
                            'profit_loss': profit_loss,
                            'profit_loss_rate': profit_loss_rate,
                            'estimate_change_rate': estimate_change_rate,
                            'estimate_profit': estimate_profit,
                            'estimate_time': '',
                            'daily_change_rate': daily_change_rate,
                            'fsrq': fsrq,
                            'one_month_rate': one_month_rate,
                            'tags': tags,
                            'platform': holding.platform or '默认'
                        })
            except Exception as e:
                logger.error(f"处理持仓数据时发生异常: {e}")
                # 即使发生异常，也返回已处理的数据，避免返回空数组
                logger.warning(f"异常发生前已处理 {len(holding_list)} 个持仓数据，返回部分结果")

            logger.info(f"返回 {len(holding_list)} 个持仓数据")
            return jsonify(holding_list)

        elif request.method == 'POST':
            data = request.json
            fund_code = data.get('fund_code')
            transaction_type = data.get('type', 'buy')
            tags = data.get('tags', '')

            if not fund_code:
                return jsonify({'error': '基金代码不能为空'}), 400

            fund = get_or_create_fund(db, fund_code)

            if not fund:
                return jsonify({'error': '获取基金信息失败'}), 404

            if tags:
                watchlist_item = db.query(Watchlist).filter(Watchlist.fund_id == fund.id, Watchlist.user_id == user_id).first()
                if not watchlist_item:
                    watchlist_item = Watchlist(fund_id=fund.id, user_id=user_id, tags=tags)
                    db.add(watchlist_item)
                else:
                    watchlist_item.tags = tags

            platform = data.get('platform', '默认')
            if not platform:
                platform = '默认'
            logger.info(f"收到的平台参数: {platform}")

            fund_holding = db.query(FundHolding).filter(
                FundHolding.fund_id == fund.id,
                FundHolding.user_id == user_id,
                FundHolding.platform == platform
            ).first()

            actual_platform = platform
            logger.info(f"查询持仓: fund_id={fund.id}, platform={platform}, 结果: {fund_holding is not None}")

            # 获取当前价格（根据日期获取净值）
            current_price = None

            # 无论交易类型是什么，都获取当前价格
            # 对于买入卖出操作，尝试根据日期获取净值
            buy_date = data.get('buy_date')
            sell_date = data.get('sell_date')

            # 确定使用的日期
            transaction_date = buy_date or sell_date

            # 尝试获取历史净值
            if transaction_date:
                # 根据日期获取净值
                logger.info(f"尝试获取基金 {fund_code} 在 {transaction_date} 的净值")
                # 调用新添加的方法获取历史净值
                history_data = DataFetcher.get_fund_history_by_date(fund_code, transaction_date)
                if history_data and history_data.get('unit_net_value'):
                    current_price = float(history_data.get('unit_net_value'))
                    logger.info(f"使用历史净值，基金代码: {fund_code}, 日期: {transaction_date}, 净值: {current_price}")
                else:
                    # 如果没有找到历史净值，使用最新净值
                    logger.warning(f"无法获取基金 {fund_code} 在 {transaction_date} 的历史净值，使用最新净值")
                    current_price = None

            # 如果没有指定日期或无法获取指定日期的净值，使用数据库缓存净值
            if not current_price:
                realtime_data = db.query(FundRealtimeData).filter(FundRealtimeData.fund_id == fund.id).first()
                if realtime_data and realtime_data.unit_net_value:
                    current_price = float(realtime_data.unit_net_value)
                    logger.info(f"使用数据库缓存净值，基金代码: {fund_code}, 净值: {current_price}")
                else:
                    current_price = 1.0
                    logger.warning(f"无法获取净值数据，基金代码: {fund_code}, 使用默认值: {current_price}")

            # 为所有交易类型定义 unit_net_value
            unit_net_value = current_price
            logger.info(f"unit_net_value: {unit_net_value}")

            if transaction_type == 'sync':
                # 同步持仓操作
                # 从前端接收current_value和profit，结合最新净值计算份额
                current_value = data.get('current_value', 0)
                profit = data.get('profit', 0)

                # 验证持仓金额
                if current_value <= 0:
                    return jsonify({'error': '持仓金额必须大于0'}), 400

                # 直接从数据库读取净值，避免同步请求外部API
                realtime_data = db.query(FundRealtimeData).filter(FundRealtimeData.fund_id == fund.id).first()
                unit_net_value = None
                if realtime_data and realtime_data.unit_net_value:
                    unit_net_value = realtime_data.unit_net_value
                    logger.info(f"使用数据库缓存净值，基金代码: {fund_code}, 净值: {unit_net_value}")

                if not unit_net_value:
                    unit_net_value = 1.0
                    logger.warning(f"无法获取净值数据，基金代码: {fund_code}, 使用默认值: {unit_net_value}")
                else:
                    unit_net_value = float(unit_net_value)

                unit_net_value = float(unit_net_value)

                # 计算持仓成本：持仓金额 - 持有收益
                cost = current_value - profit

                if fund_holding:
                    # 根据新的持仓金额和最新净值重新计算份额
                    shares = current_value / unit_net_value if unit_net_value > 0 else 0
                    # 计算平均成本
                    avg_cost = cost / shares if shares > 0 else 0
                    # 计算收益率
                    profit_rate = 0
                    if cost > 0:
                        profit_rate = (profit / cost) * 100

                    logger.info(f"同步持仓 - 基金代码: {fund_code}, 平台: {platform}")
                    logger.info(f"输入数据: 持仓金额={current_value}, 持有收益={profit}")
                    logger.info(f"计算数据: 净值={unit_net_value}, 份额={shares}, 成本={cost}, 平均成本={avg_cost}")

                    # 更新持仓
                    fund_holding.cost = cost
                    fund_holding.shares = shares
                    fund_holding.avg_cost = avg_cost
                    fund_holding.current_value = current_value
                    fund_holding.profit_loss = profit
                    fund_holding.profit_loss_rate = profit_rate
                    fund_holding.platform = platform
                else:
                    # 新增持仓时，根据当前净值计算初始份额
                    shares = current_value / unit_net_value if unit_net_value > 0 else 0
                    avg_cost = cost / shares if shares > 0 else 0
                    profit_rate = 0
                    if cost > 0:
                        profit_rate = (profit / cost) * 100

                    logger.info(f"添加持仓 - 基金代码: {fund_code}, 平台: {platform}")
                    logger.info(f"输入数据: 持仓金额={current_value}, 持有收益={profit}")
                    logger.info(f"计算数据: 净值={unit_net_value}, 份额={shares}, 成本={cost}, 平均成本={avg_cost}")

                    fund_holding = FundHolding(
                        fund_id=fund.id,
                        user_id=user_id,
                        cost=cost,
                        shares=shares,
                        avg_cost=avg_cost,
                        current_value=current_value,
                        profit_loss=profit,
                        profit_loss_rate=profit_rate,
                        platform=platform
                    )
                    db.add(fund_holding)
            elif transaction_type == 'buy':
                # 买入操作
                cost = data.get('cost', 0)
                buy_date = data.get('buy_date')

                if cost <= 0:
                    return jsonify({'error': '金额不能为空且必须大于0'}), 400

                shares = cost / unit_net_value

                if fund_holding:
                    # 更新持仓
                    total_cost = fund_holding.cost + cost
                    total_shares = fund_holding.shares + shares
                    fund_holding.cost = total_cost
                    fund_holding.shares = total_shares
                    fund_holding.avg_cost = total_cost / total_shares
                else:
                    fund_holding = FundHolding(
                        fund_id=fund.id,
                        user_id=user_id,
                        cost=cost,
                        shares=shares,
                        avg_cost=unit_net_value,
                        platform=platform
                    )
                    db.add(fund_holding)

                platform_obj = db.query(Platform).filter(Platform.name == actual_platform, Platform.user_id == user_id).first()
                if not platform_obj:
                    platform_obj = Platform(name=actual_platform, user_id=user_id)
                    db.add(platform_obj)
                    db.flush()
                platform_id = platform_obj.id

                transaction = Transaction(
                    fund_id=fund.id,
                    user_id=user_id,
                    platform_id=platform_id,
                    transaction_type=transaction_type,
                    amount=cost,
                    shares=shares,
                    price=current_price
                )
                if buy_date:
                    transaction.transaction_date = datetime.strptime(buy_date, '%Y-%m-%d')
                db.add(transaction)

            elif transaction_type == 'sell':
                # 卖出操作，使用前端传递的份额
                shares = data.get('shares', 0)
                sell_date = data.get('sell_date')

                logger.info(f"减仓操作 - 基金代码: {fund_code}, 平台: {platform}")
                logger.info(f"输入数据: 份额={shares}, 卖出日期={sell_date}")
                logger.info(f"当前持仓: 份额={fund_holding.shares if fund_holding else 'None'}, 成本={fund_holding.cost if fund_holding else 'None'}")

                # 确保shares是浮点数类型
                try:
                    shares = float(shares)
                except (TypeError, ValueError):
                    return jsonify({'error': '份额格式错误'}), 400

                logger.info(f"转换后份额: {shares}, current_price: {current_price}")

                if shares <= 0:
                    return jsonify({'error': '份额不能为空且必须大于0'}), 400

                if not fund_holding or fund_holding.shares < shares - 0.01:
                    logger.error(f"持仓份额不足: 持仓份额={fund_holding.shares if fund_holding else 'None'}, 减仓份额={shares}")
                    return jsonify({'error': '持仓份额不足'}), 400

                # 计算卖出金额
                amount = shares * current_price

                # 计算卖出份额占总份额的比例
                sell_ratio = shares / fund_holding.shares

                # 更新持仓：按比例减少持仓成本
                fund_holding.cost = fund_holding.cost * (1 - sell_ratio)
                fund_holding.shares -= shares
                logger.info(f"减仓后 - 剩余份额: {fund_holding.shares}, 剩余成本: {fund_holding.cost}")
                if fund_holding.shares <= 0.01 or fund_holding.cost <= 0.01:
                    # 清空持仓 - 先删除相关的收益历史记录
                    logger.info(f"清仓 - 基金代码: {fund_code}, 平台: {platform}")
                    from models import HoldingProfitHistory
                    db.query(HoldingProfitHistory).filter(HoldingProfitHistory.holding_id == fund_holding.id).delete()
                    db.delete(fund_holding)
                    fund_holding = None
                else:
                    # 重新计算平均成本（应该保持不变）
                    fund_holding.avg_cost = fund_holding.cost / fund_holding.shares

                platform_obj = db.query(Platform).filter(Platform.name == actual_platform, Platform.user_id == user_id).first()
                if not platform_obj:
                    platform_obj = Platform(name=actual_platform, user_id=user_id)
                    db.add(platform_obj)
                    db.flush()
                platform_id = platform_obj.id

                transaction = Transaction(
                    fund_id=fund.id,
                    user_id=user_id,
                    platform_id=platform_id,
                    transaction_type=transaction_type,
                    amount=amount,
                    shares=shares,
                    price=current_price
                )
                if sell_date:
                    transaction.transaction_date = datetime.strptime(sell_date, '%Y-%m-%d')
                db.add(transaction)

            # 计算并更新持仓信息（仅对于非同步持仓操作）
            if fund_holding and transaction_type != 'sync':
                calculate_holding(fund_holding, current_price)

            db.commit()

            # 对于加仓/减仓操作，返回更新后的持仓数据
            if transaction_type in ('buy', 'sell') and fund_holding:
                # 直接从数据库读取基金数据，避免同步请求外部API
                rt_data = db.query(FundRealtimeData).filter(FundRealtimeData.fund_id == fund.id).first()
                # 获取标签
                watchlist_item = db.query(Watchlist).filter(Watchlist.fund_id == fund.id).first()
                tags = watchlist_item.tags if watchlist_item else ''

                if rt_data:
                    unit_net_value = rt_data.unit_net_value
                    fsrq = rt_data.fsrq or ''
                    daily_change_rate = rt_data.daily_change_rate or '-'
                    estimate_change_rate = str(rt_data.estimate_change_rate) if rt_data.estimate_change_rate is not None else '-'

                    if unit_net_value:
                        current_value = fund_holding.shares * float(unit_net_value)

                        # 检查最新涨幅是否已更新（fsrq是否为今日）
                        today = now_cst_naive().strftime('%Y-%m-%d')
                        is_today = (fsrq == today)

                        # 检查估算涨幅日期是否为今日
                        estimate_time = rt_data.estimate_time or ''
                        estimate_is_today = False
                        if estimate_time:
                            estimate_date = estimate_time.split(' ')[0] if ' ' in estimate_time else estimate_time
                            estimate_is_today = (estimate_date == today)

                        # 逻辑：
                        # 1. 最新涨幅已更新（is_today为true），优先使用最新涨幅计算
                        # 2. 最新涨幅未更新但估算涨幅是今日的，使用估算涨幅计算
                        # 3. 估算涨幅不是今日的，今日收益显示为"-"
                        if is_today and daily_change_rate not in ('-', None, '0', 0):
                            # 最新涨幅已更新，unit_net_value已是今日净值，current_value已包含今日涨幅
                            change_rate = float(daily_change_rate)
                            estimate_profit = current_value * (change_rate / (100 + change_rate))
                        elif estimate_is_today and estimate_change_rate not in ('-', None, '0', 0):
                            # 估算涨幅是今日的，使用估算涨幅计算今日收益
                            change_rate = float(estimate_change_rate)
                            estimate_profit = current_value * (change_rate / 100)
                        else:
                            # 估算涨幅不是今日的，今日收益显示为"-"
                            estimate_profit = None
                            if not estimate_is_today:
                                estimate_change_rate = '-'
                    else:
                        current_value = fund_holding.cost
                        estimate_profit = 0

                    # 实时计算持有收益和持仓金额
                    profit_loss = current_value - fund_holding.cost
                    profit_loss_rate = (profit_loss / fund_holding.cost * 100) if fund_holding.cost > 0 else 0

                    updated_holding = {
                        'fund_code': fund.fund_code,
                        'fund_name': fund.fund_name,
                        'cost': fund_holding.cost,
                        'shares': fund_holding.shares,
                        'avg_cost': fund_holding.avg_cost,
                        'current_value': current_value,
                        'profit_loss': profit_loss,
                        'profit_loss_rate': profit_loss_rate,
                        'estimate_change_rate': estimate_change_rate,
                        'estimate_profit': estimate_profit,
                        'daily_change_rate': daily_change_rate,
                        'fsrq': fsrq,
                        'one_month_rate': rt_data.one_month_rate or 0,
                        'tags': tags,
                        'platform': fund_holding.platform or '默认'
                    }
                else:
                    updated_holding = {
                        'fund_code': fund.fund_code,
                        'fund_name': fund.fund_name,
                        'cost': fund_holding.cost,
                        'shares': fund_holding.shares,
                        'avg_cost': fund_holding.avg_cost,
                        'current_value': fund_holding.current_value or fund_holding.cost,
                        'profit_loss': fund_holding.profit_loss or 0,
                        'profit_loss_rate': fund_holding.profit_loss_rate or 0,
                        'estimate_change_rate': '0.00',
                        'estimate_profit': 0,
                        'daily_change_rate': '-',
                        'fsrq': '',
                        'one_month_rate': 0,
                        'tags': tags,
                        'platform': fund_holding.platform or '默认'
                    }

                return jsonify({
                    'success': True,
                    'holding': updated_holding
                })

            return jsonify({'success': True})
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        logger.error(f"处理 /api/holding 请求时发生错误: {e}")
        logger.error(f"错误堆栈: {error_trace}")
        print(f"处理 /api/holding 请求时发生错误: {e}")
        print(f"错误堆栈: {error_trace}")
        if 'db' in locals():
            db.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        if 'db' in locals():
            db.close()

@app.route('/api/transaction/<fund_code>', methods=['GET'])
@jwt_required()
def get_transaction_history(fund_code):
    db = next(get_db())
    try:
        user_id = get_current_user_id()
        fund = db.query(Fund).filter(Fund.fund_code == fund_code).first()
        if not fund:
            return jsonify({'error': '基金不存在'}), 404

        transactions = db.query(Transaction).filter(Transaction.fund_id == fund.id, Transaction.user_id == user_id).order_by(Transaction.transaction_date.desc()).all()
        transaction_list = []
        for transaction in transactions:
            transaction_list.append({
                'id': transaction.id,
                'type': transaction.transaction_type,
                'amount': transaction.amount,
                'shares': transaction.shares,
                'price': transaction.price,
                'date': transaction.transaction_date.strftime('%Y-%m-%d %H:%M:%S'),
                'platform_id': transaction.platform_id
            })
        return jsonify(transaction_list)
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        db.close()

@app.route('/api/holding/<fund_code>/history', methods=['GET'])
@jwt_required()
def get_holding_profit_history(fund_code):
    db = next(get_db())
    try:
        user_id = get_current_user_id()
        fund = db.query(Fund).filter(Fund.fund_code == fund_code).first()
        if not fund:
            return jsonify({'error': '基金不存在'}), 404

        holding = db.query(FundHolding).filter(FundHolding.fund_id == fund.id, FundHolding.user_id == user_id).first()
        if not holding:
            return jsonify({'error': '持仓不存在'}), 404

        # 获取最近30条历史记录
        histories = db.query(HoldingProfitHistory).filter(
            HoldingProfitHistory.holding_id == holding.id
        ).order_by(HoldingProfitHistory.recorded_at.desc()).limit(30).all()

        history_list = []
        for history in histories:
            history_list.append({
                'id': history.id,
                'cost': history.cost,
                'shares': history.shares,
                'avg_cost': history.avg_cost,
                'current_value': history.current_value,
                'profit_loss': history.profit_loss,
                'profit_loss_rate': history.profit_loss_rate,
                'unit_net_value': history.unit_net_value,
                'fsrq': history.fsrq,
                'daily_change_rate': history.daily_change_rate,
                'recorded_at': history.recorded_at.strftime('%Y-%m-%d %H:%M:%S')
            })
        return jsonify(history_list)
    except Exception as e:
        logger.error(f"获取持仓收益历史失败: {e}")
        return jsonify({'error': str(e)}), 500
    finally:
        db.close()


@app.route('/api/test', methods=['GET'])
def test_api():
    """
    测试API端点
    """
    from datetime import datetime
    print(f"[{datetime.now()}] 收到 /api/test 请求")
    return jsonify({'message': '测试API正常工作', 'timestamp': datetime.now().isoformat()})

@app.route('/api/holding/<fund_code>', methods=['DELETE'])
@jwt_required()
def delete_holding(fund_code):
    db = next(get_db())
    try:
        user_id = get_current_user_id()
        fund = db.query(Fund).filter(Fund.fund_code == fund_code).first()
        if not fund:
            return jsonify({'error': '基金不存在'}), 404

        fund_holding = db.query(FundHolding).filter(FundHolding.fund_id == fund.id, FundHolding.user_id == user_id).first()
        if not fund_holding:
            return jsonify({'error': '持仓不存在'}), 404

        from models import HoldingProfitHistory
        db.query(HoldingProfitHistory).filter(HoldingProfitHistory.holding_id == fund_holding.id).delete()
        db.delete(fund_holding)
        db.commit()
        return jsonify({'success': True})
    except Exception as e:
        db.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        db.close()

@app.route('/api/holding/<fund_code>', methods=['PUT'])
@jwt_required()
def update_holding(fund_code):
    db = next(get_db())
    try:
        user_id = get_current_user_id()
        data = request.json
        current_value = data.get('current_value', 0)
        profit = data.get('profit', 0)
        platform = data.get('platform', '默认')

        if current_value <= 0:
            return jsonify({'error': '持仓金额不能为空且必须大于0'}), 400

        # 获取基金
        fund = db.query(Fund).filter(Fund.fund_code == fund_code).first()
        if not fund:
            return jsonify({'error': '基金不存在'}), 404

        # 直接从数据库读取净值，避免同步请求外部API导致超时
        # 修改持仓不需要实时净值，数据库缓存即可满足计算需求
        realtime_data = db.query(FundRealtimeData).filter(FundRealtimeData.fund_id == fund.id).first()
        unit_net_value = None
        if realtime_data and realtime_data.unit_net_value:
            unit_net_value = realtime_data.unit_net_value
        else:
            return jsonify({'error': '无法获取净值数据，请先刷新基金数据'}), 404

        # 计算持仓成本：持仓金额 - 持有收益
        cost = current_value - profit

        fund_holding = db.query(FundHolding).filter(
            FundHolding.fund_id == fund.id,
            FundHolding.user_id == user_id,
            FundHolding.platform == platform
        ).first()
        if not fund_holding:
            logger.warning(f"持仓不存在，基金ID: {fund.id}, 平台: {platform}")
            return jsonify({'error': '持仓不存在'}), 404

        # 根据新的持仓金额和最新净值重新计算份额
        # 保持 持仓金额 = 份额 × 最新净值 的关系
        shares = current_value / float(unit_net_value) if float(unit_net_value) > 0 else 0
        # 计算平均成本
        avg_cost = cost / shares if shares > 0 else 0
        # 计算收益率
        profit_rate = 0
        if cost > 0:
            profit_rate = (profit / cost) * 100

        # 记录更新前的数据
        logger.info(f"更新前 - 持仓ID: {fund_holding.id}, 成本: {fund_holding.cost}, 份额: {fund_holding.shares}, 当前价值: {fund_holding.current_value}, 持有收益: {fund_holding.profit_loss}, 平台: {fund_holding.platform}")
        logger.info(f"更新后 - 成本: {cost}, 份额: {shares}, 当前价值: {current_value}, 持有收益: {profit}, 平台: {platform}")

        # 更新持仓
        fund_holding.cost = cost
        fund_holding.shares = shares
        fund_holding.avg_cost = avg_cost
        fund_holding.current_value = current_value
        fund_holding.profit_loss = profit
        fund_holding.profit_loss_rate = profit_rate
        fund_holding.platform = platform

        db.commit()
        return jsonify({'success': True})
    except Exception as e:
        db.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        db.close()

@app.route('/api/watchlist/tags', methods=['PUT'])
@jwt_required()
def update_watchlist_tags():
    db = next(get_db())
    try:
        user_id = get_current_user_id()
        data = request.json
        fund_code = data.get('fund_code')
        tags = data.get('tags', '')

        if not fund_code:
            return jsonify({'error': '基金代码不能为空'}), 400

        fund = db.query(Fund).filter(Fund.fund_code == fund_code).first()
        if not fund:
            return jsonify({'error': '基金不存在'}), 404

        watchlist_item = db.query(Watchlist).filter(Watchlist.fund_id == fund.id, Watchlist.user_id == user_id).first()
        if not watchlist_item:
            watchlist_item = Watchlist(fund_id=fund.id, user_id=user_id, tags=tags)
            db.add(watchlist_item)
        else:
            watchlist_item.tags = tags

        db.commit()
        return jsonify({'success': True})
    except Exception as e:
        db.rollback()
        print(f"更新自选基金标签时出错: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500
    finally:
        db.close()

@app.route('/api/holding/tags', methods=['PUT'])
@jwt_required()
def update_holding_tags():
    db = next(get_db())
    try:
        user_id = get_current_user_id()
        data = request.json
        fund_code = data.get('fund_code')
        tags = data.get('tags', '')

        if not fund_code:
            return jsonify({'error': '基金代码不能为空'}), 400

        fund = db.query(Fund).filter(Fund.fund_code == fund_code).first()
        if not fund:
            return jsonify({'error': '基金不存在'}), 404

        watchlist_item = db.query(Watchlist).filter(Watchlist.fund_id == fund.id, Watchlist.user_id == user_id).first()
        if not watchlist_item:
            watchlist_item = Watchlist(fund_id=fund.id, user_id=user_id, tags=tags)
            db.add(watchlist_item)
        else:
            watchlist_item.tags = tags

        db.commit()
        return jsonify({'success': True})
    except Exception as e:
        db.rollback()
        print(f"更新持仓基金标签时出错: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500
    finally:
        db.close()

@app.route('/api/holding/codes', methods=['GET'])
@jwt_required(optional=True)
def get_holding_codes():
    db = next(get_db())
    try:
        user_id = get_current_user_id()
        if not user_id:
            return jsonify({'fund_codes': []})
        holdings = db.query(FundHolding).filter(FundHolding.user_id == user_id).all()
        fund_codes = [holding.fund.fund_code for holding in holdings]
        return jsonify({'fund_codes': fund_codes})
    except Exception as e:
        print(f"获取持仓基金代码失败: {e}")
        return jsonify({'fund_codes': []})
    finally:
        db.close()

@app.route('/api/tags', methods=['GET'])
@jwt_required()
def get_all_tags():
    db = next(get_db())
    try:
        user_id = get_current_user_id()
        watchlist_items = db.query(Watchlist).filter(Watchlist.user_id == user_id).all()
        tags_set = set()

        for item in watchlist_items:
            if item.tags:
                item_tags = [tag.strip() for tag in item.tags.split(',')]
                tags_set.update(item_tags)

        tags = sorted(list(tags_set))
        return jsonify({'tags': tags})
    except Exception as e:
        print(f"获取标签失败: {e}")
        return jsonify({'tags': []})
    finally:
        db.close()

@app.route('/api/platform', methods=['GET'])
@jwt_required()
def get_platforms():
    db = next(get_db())
    try:
        user_id = get_current_user_id()
        platforms = db.query(Platform).filter(Platform.user_id == user_id).order_by(Platform.order_num, Platform.id).all()
        platform_list = [{'id': p.id, 'name': p.name} for p in platforms]
        return jsonify(platform_list)
    except Exception as e:
        db.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        db.close()

@app.route('/api/platform', methods=['POST'])
@jwt_required()
def add_platform():
    data = request.json
    name = data.get('name')
    if not name:
        return jsonify({'error': '平台名称不能为空'}), 400

    db = next(get_db())
    try:
        user_id = get_current_user_id()
        existing = db.query(Platform).filter(Platform.name == name, Platform.user_id == user_id).first()
        if existing:
            return jsonify({'error': '平台已存在'}), 400

        max_order = db.query(Platform).filter(Platform.user_id == user_id).with_entities(func.max(Platform.order_num)).scalar() or 0

        platform = Platform(name=name, user_id=user_id, order_num=max_order + 1)
        db.add(platform)
        db.commit()
        db.refresh(platform)
        return jsonify({'success': True, 'id': platform.id, 'name': platform.name})
    except Exception as e:
        db.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        db.close()

@app.route('/api/platform/<int:platform_id>', methods=['PUT'])
@jwt_required()
def update_platform(platform_id):
    db = next(get_db())
    try:
        user_id = get_current_user_id()
        data = request.json
        name = data.get('name', '').strip()

        if not name:
            return jsonify({'error': '平台名称不能为空'}), 400

        platform = db.query(Platform).filter(Platform.id == platform_id, Platform.user_id == user_id).first()
        if not platform:
            return jsonify({'error': '平台不存在'}), 404

        existing = db.query(Platform).filter(Platform.name == name, Platform.user_id == user_id, Platform.id != platform_id).first()
        if existing:
            return jsonify({'error': '平台名称已存在'}), 400

        old_name = platform.name
        platform.name = name

        holdings = db.query(FundHolding).filter(FundHolding.platform == old_name, FundHolding.user_id == user_id).all()
        for holding in holdings:
            holding.platform = name

        db.commit()

        return jsonify({'success': True})
    except Exception as e:
        db.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        db.close()

@app.route('/api/platform/<int:platform_id>', methods=['DELETE'])
@jwt_required()
def delete_platform(platform_id):
    db = next(get_db())
    try:
        user_id = get_current_user_id()
        platform = db.query(Platform).filter(Platform.id == platform_id, Platform.user_id == user_id).first()
        if not platform:
            return jsonify({'error': '平台不存在'}), 404

        holdings = db.query(FundHolding).filter(FundHolding.platform == platform.name, FundHolding.user_id == user_id).all()
        if holdings:
            return jsonify({'error': f'该平台下有{len(holdings)}个持仓，无法删除'}), 400

        db.query(Transaction).filter(Transaction.platform_id == platform_id, Transaction.user_id == user_id).delete(synchronize_session=False)

        db.delete(platform)
        db.commit()
        return jsonify({'success': True})
    except Exception as e:
        db.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        db.close()

@app.route('/api/platform/order', methods=['PUT'])
@jwt_required()
def update_platform_order():
    data = request.json
    order_data = data.get('order', [])

    if not order_data:
        return jsonify({'error': '排序数据不能为空'}), 400

    db = next(get_db())
    try:
        user_id = get_current_user_id()
        for item in order_data:
            platform_id = item.get('id')
            order = item.get('order')

            if platform_id and order is not None:
                platform = db.query(Platform).filter(Platform.id == platform_id, Platform.user_id == user_id).first()
                if platform:
                    platform.order_num = order

        db.commit()
        return jsonify({'success': True})
    except Exception as e:
        db.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        db.close()

# 全局错误处理器
@app.errorhandler(Exception)
def handle_exception(e):
    import traceback
    error_trace = traceback.format_exc()
    logger.error(f"未处理的异常: {e}")
    logger.error(f"错误堆栈: {error_trace}")
    print(f"未处理的异常: {e}")
    print(f"错误堆栈: {error_trace}")
    return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--host', default='0.0.0.0', help='Host to bind to')
    parser.add_argument('--port', type=int, default=5000, help='Port to bind to')
    args = parser.parse_args()

    try:
        app.run(debug=False, host=args.host, port=args.port, use_reloader=False)
    except (KeyboardInterrupt, SystemExit):
        scheduler.shutdown()
        print("定时任务调度器已关闭")
