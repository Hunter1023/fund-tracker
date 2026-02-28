from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from data_fetcher import DataFetcher
from models import Fund, FundHolding, Transaction, Watchlist, FundRealtimeData, HoldingProfitHistory, Platform, create_tables, get_db
from sqlalchemy.orm import Session
from sqlalchemy import func
import decimal
import time
import json
import logging
import os
from datetime import datetime, timedelta
from apscheduler.schedulers.background import BackgroundScheduler
import threading
from sqlalchemy.exc import OperationalError
import random

app = Flask(__name__)
# 从环境变量获取数据库路径，没有则用默认
db_path = os.getenv('DATABASE_PATH', 'fund_tracker.db')
app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_path}'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)
CORS(app)

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
    数据库操作重试装饰器，用于处理SQLite锁定问题
    """
    def decorator(func):
        def wrapper(*args, **kwargs):
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except OperationalError as e:
                    if 'database is locked' in str(e) and attempt < max_retries - 1:
                        delay = base_delay * (2 ** attempt) + random.uniform(0, 0.1)
                        logger.warning(f"数据库锁定，第{attempt + 1}次重试，等待{delay:.2f}秒...")
                        time.sleep(delay)
                    else:
                        raise
        return wrapper
    return decorator

# 创建数据库表
create_tables()

# 初始化默认平台
def init_default_platform():
    """
    初始化默认平台，如果不存在则创建
    """
    db = next(get_db())
    try:
        # 检查是否已存在"默认"平台
        existing_platform = db.query(Platform).filter(Platform.name == '默认').first()
        if not existing_platform:
            # 创建默认平台
            default_platform = Platform(
                name='默认',
                order=0
            )
            db.add(default_platform)
            db.commit()
            print("已创建默认平台")
        else:
            print("默认平台已存在")
    except Exception as e:
        db.rollback()
        print(f"初始化默认平台时出错: {e}")
    finally:
        db.close()

# 执行初始化
init_default_platform()

# 创建定时任务调度器
scheduler = BackgroundScheduler()
scheduler.start()

# 定时任务：更新所有基金数据
@retry_db_operation()
def update_all_funds_data():
    """
    定时任务：更新所有自选基金和持仓基金的实时数据
    """
    print(f"[{datetime.now()}] 开始更新基金数据...")
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
        
        print(f"需要更新 {len(fund_codes)} 个基金的数据")
        
        # 更新每个基金的数据
        for fund_code in fund_codes:
            try:
                # 强制刷新数据
                get_fund_realtime_data(db, fund_code, force_refresh=True)
                print(f"成功更新基金 {fund_code} 的数据")
            except Exception as e:
                print(f"更新基金 {fund_code} 数据失败: {e}")
        
        print(f"[{datetime.now()}] 基金数据更新完成")
    except Exception as e:
        print(f"定时任务执行失败: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

# 添加定时任务：每10分钟更新一次
scheduler.add_job(update_all_funds_data, 'interval', minutes=10, id='update_funds_data')

# 辅助函数：判断是否为交易日
def is_trading_day(fsrq: str) -> bool:
    """
    判断是否为交易日（通过净值日期判断）
    :param fsrq: 净值日期，格式为YYYY-MM-DD
    :return: 是否为交易日
    """
    if not fsrq:
        return False
    today = datetime.now().strftime('%Y-%m-%d')
    return fsrq == today

# 定时任务：更新持仓收益
@retry_db_operation()
def update_holding_profit():
    """
    定时任务：在交易日晚上7点开始，每10分钟检测一次最新涨幅是否已更新，
    更新所有持仓基金的持有收益到数据库
    """
    current_time = datetime.now()
    current_hour = current_time.hour
    
    # 只在晚上7点到11点之间执行
    if current_hour < 19 or current_hour >= 23:
        return
    
    logger.info(f"开始检查持仓收益更新...")
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
            
            # 检查是否为交易日（fsrq是否为当日）
            fsrq = fund_data.get('fsrq', '')
            if not is_trading_day(fsrq):
                logger.info(f"基金 {fund_code} 净值日期 {fsrq} 不是今日，跳过")
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

# 添加定时任务：每10分钟执行一次持仓收益更新检查
scheduler.add_job(update_holding_profit, 'interval', minutes=10, id='update_holding_profit')

print("定时任务已启动：每10分钟更新一次基金数据")
print("定时任务已启动：每10分钟检查一次持仓收益更新（交易日19:00-23:00）")

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

def get_fund_realtime_rates_batch(db: Session, fund_codes: list, force_refresh=False):
    """
    批量并发获取基金实时涨跌幅数据（不获取历史净值数组，用于自选列表）
    :param db: 数据库会话
    :param fund_codes: 基金代码列表
    :param force_refresh: 是否强制刷新
    :return: 基金实时涨跌幅数据字典 {fund_code: data}
    """
    if not fund_codes:
        return {}
    
    results = {}
    
    # 分离需要刷新的基金和不需要刷新的基金
    funds_to_refresh = []
    funds_from_db = {}
    
    for fund_code in fund_codes:
        fund = db.query(Fund).filter(Fund.fund_code == fund_code).first()
        if not fund:
            continue
        
        # 检查数据库中是否有实时数据
        realtime_data = db.query(FundRealtimeData).filter(FundRealtimeData.fund_id == fund.id).first()
        
        # 如果强制刷新或数据不存在或数据过期（超过10分钟），则需要刷新
        need_refresh = force_refresh
        if not need_refresh and realtime_data:
            if realtime_data.updated_at:
                time_diff = datetime.now() - realtime_data.updated_at
                if time_diff > timedelta(minutes=10):
                    need_refresh = True
        
        if need_refresh:
            funds_to_refresh.append(fund_code)
        elif realtime_data:
            # 从数据库读取数据
            funds_from_db[fund_code] = {
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
                'net_values': []
            }
        else:
            # 数据库中没有数据，也需要刷新
            funds_to_refresh.append(fund_code)
    
    # 并发获取需要刷新的基金数据
    if funds_to_refresh:
        # 使用小时级时间戳作为缓存键，每1小时更新一次
        cache_key = int(time.time() / (60 * 60))
        
        # 并发获取估值数据
        valuation_data_dict = DataFetcher.get_fund_valuation_batch(funds_to_refresh, cache_key)
        # 并发获取涨跌幅数据
        rates_data_dict = DataFetcher.get_fund_rates_batch(funds_to_refresh, cache_key)
        
        # 处理数据并更新数据库
        for fund_code in funds_to_refresh:
            fund = db.query(Fund).filter(Fund.fund_code == fund_code).first()
            if not fund:
                continue
            
            fund_data = valuation_data_dict.get(fund_code)
            rates_data = rates_data_dict.get(fund_code)
            
            if rates_data:
                # 准备数据
                data = {
                    'fund_code': fund_code,
                    'fund_name': fund.fund_name,
                    'net_value_date': fund_data.get('net_value') if fund_data else rates_data.get('fsrq', ''),
                    'unit_net_value': float(fund_data.get('unit_net_value', 0)) if fund_data else None,
                    'estimate_net_value': float(fund_data.get('estimate_net_value', 0)) if fund_data else None,
                    'estimate_change_rate': float(fund_data.get('estimate_change_rate', 0)) if fund_data else None,
                    'estimate_time': fund_data.get('estimate_time', '') if fund_data else '',
                    'one_month_rate': rates_data.get('one_month_rate', 0),
                    'three_month_rate': rates_data.get('three_month_rate', 0),
                    'one_year_rate': rates_data.get('one_year_rate', 0),
                    'daily_change_rate': rates_data.get('daily_change_rate', 0),
                    'fsrq': rates_data.get('fsrq', ''),
                    'net_values': '[]'
                }
                
                # 检查或创建实时数据记录
                realtime_data = db.query(FundRealtimeData).filter(FundRealtimeData.fund_id == fund.id).first()
                
                if realtime_data:
                    for key, value in data.items():
                        if key != 'fund_code' and key != 'fund_name':
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
                
                db.flush()
                db.refresh(realtime_data)
                
                # 添加到结果
                results[fund_code] = {
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
                    'net_values': []
                }
            else:
                # API调用失败，返回基本信息
                results[fund_code] = {
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
    
    # 合并数据库中的数据
    results.update(funds_from_db)
    
    return results

def get_fund_realtime_rates(db: Session, fund_code: str, force_refresh=False):
    """
    获取基金实时涨跌幅数据（不获取历史净值数组，用于自选列表）
    :param db: 数据库会话
    :param fund_code: 基金代码
    :param force_refresh: 是否强制刷新
    :return: 基金实时涨跌幅数据字典
    """
    fund = db.query(Fund).filter(Fund.fund_code == fund_code).first()
    if not fund:
        return None
    
    # 检查数据库中是否有实时数据
    realtime_data = db.query(FundRealtimeData).filter(FundRealtimeData.fund_id == fund.id).first()
    
    # 如果强制刷新或数据不存在或数据过期（超过10分钟），则从API获取
    need_refresh = force_refresh
    fund_data = None
    rates_data = None
    if not need_refresh and realtime_data:
        # 检查数据是否过期（10分钟）
        if realtime_data.updated_at:
            time_diff = datetime.now() - realtime_data.updated_at
            if time_diff > timedelta(minutes=10):
                need_refresh = True
    
    if need_refresh:
        # 从API获取数据
        # 使用分钟级时间戳作为缓存键，每5分钟更新一次
        cache_key = int(time.time() / (5 * 60))
        fund_data = DataFetcher.get_fund_valuation(fund_code, cache_key)
        rates_data = DataFetcher.get_fund_rates(fund_code, cache_key)
        
        # 只要rates_data有数据，就处理
        if rates_data:
            # 准备数据
            data = {
                'fund_code': fund_code,
                'fund_name': fund.fund_name,
                'net_value_date': fund_data.get('net_value') if fund_data else rates_data.get('fsrq', ''),
                'unit_net_value': float(fund_data.get('unit_net_value', 0)) if fund_data else None,
                'estimate_net_value': float(fund_data.get('estimate_net_value', 0)) if fund_data else None,
                'estimate_change_rate': float(fund_data.get('estimate_change_rate', 0)) if fund_data else None,
                'estimate_time': fund_data.get('estimate_time', '') if fund_data else '',
                'one_month_rate': rates_data.get('one_month_rate', 0),
                'three_month_rate': rates_data.get('three_month_rate', 0),
                'one_year_rate': rates_data.get('one_year_rate', 0),
                'daily_change_rate': rates_data.get('daily_change_rate', 0),
                'fsrq': rates_data.get('fsrq', ''),
                'net_values': '[]'  # 不存储历史净值数组
            }
            
            # 更新或创建数据库记录（添加重试机制）
            @retry_db_operation(max_retries=5, base_delay=0.2)
            def update_realtime_data():
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
                db.flush()
                db.refresh(realtime_data)
                return realtime_data
            
            realtime_data = update_realtime_data()
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
                # 返回数据库中的旧数据
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
            'net_values': []
        }
    
    # 返回格式化的数据
    if need_refresh and (fund_data or rates_data):
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
            'net_values': []
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
            'net_values': []
        }

@retry_db_operation()
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
    fund = db.query(Fund).filter(Fund.fund_code == fund_code).first()
    if not fund:
        return None
    
    # 检查数据库中是否有实时数据
    realtime_data = db.query(FundRealtimeData).filter(FundRealtimeData.fund_id == fund.id).first()
    
    # 如果强制刷新或数据不存在或数据过期（超过10分钟），则从API获取
    need_refresh = force_refresh
    fund_data = None
    history_data = None
    if not need_refresh and realtime_data:
        # 检查数据是否过期（10分钟）
        if realtime_data.updated_at:
            time_diff = datetime.now() - realtime_data.updated_at
            if time_diff > timedelta(minutes=10):
                need_refresh = True
    
    if need_refresh:
        # 从API获取数据
        fund_data = DataFetcher.get_fund_valuation(fund_code, int(time.time()))
        
        # 只在需要时获取历史数据
        if need_history_data:
            # 只获取必要的涨跌幅数据，不获取完整的历史净值数组
            history_data = DataFetcher.get_fund_history(fund_code)
        else:
            # 不需要历史数据时，只获取涨跌幅数据
            # 这里我们可以使用一个简化的API调用，只获取基本信息
            history_data = DataFetcher.get_fund_history_simple(fund_code)
        
        # 即使fund_data为None，只要history_data有数据，就处理
        if history_data:
            # 准备数据
            data = {
                'fund_code': fund_code,
                'fund_name': fund.fund_name,
                'net_value_date': fund_data.get('net_value') if fund_data else history_data.get('fsrq', ''),
                'unit_net_value': float(fund_data.get('unit_net_value', 0)) if fund_data else float(history_data.get('unit_net_value', 0)),
                'estimate_net_value': float(fund_data.get('estimate_net_value', 0)) if fund_data else None,
                'estimate_change_rate': float(fund_data.get('estimate_change_rate', 0)) if fund_data else None,
                'estimate_time': fund_data.get('estimate_time', '') if fund_data else '',
                'one_month_rate': history_data.get('one_month_rate', 0),
                'three_month_rate': history_data.get('three_month_rate', 0),
                'one_year_rate': history_data.get('one_year_rate', 0),
                'daily_change_rate': history_data.get('daily_change_rate', 0),
                'fsrq': history_data.get('fsrq', ''),
                'net_values': json.dumps(history_data.get('net_values', []))
            }
            
            # 更新或创建数据库记录
            if not skip_db_write:
                if realtime_data:
                    for key, value in data.items():
                        if key != 'fund_code' and key != 'fund_name':
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
                
                db.flush()
                db.refresh(realtime_data)
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
    if need_refresh and (fund_data or history_data):
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
    :param fund_code: 基金代码
    :return: 基金详情
    """
    try:
        # 获取基金估值数据
        fund_data = DataFetcher.get_fund_valuation(fund_code)
    except Exception as e:
        print(f"获取基金估值失败: {e}")
        fund_data = None
    
    try:
        # 获取基金历史净值和涨跌幅数据
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
            'fund_name': '',
            'net_value': '',
            'unit_net_value': None,
            'estimate_net_value': None,
            'estimate_change_rate': '-',
            'estimate_time': ''
        }
    
    # 获取基金重仓股数据
    try:
        holdings = DataFetcher.get_fund_holding(fund_code)
        fund_data['holdings'] = holdings
    except Exception as e:
        print(f"获取基金重仓股失败: {e}")
        fund_data['holdings'] = []
    
    # 添加历史数据
    if history_data:
        fund_data['one_month_rate'] = history_data.get('one_month_rate', 0)
        fund_data['three_month_rate'] = history_data.get('three_month_rate', 0)
        fund_data['one_year_rate'] = history_data.get('one_year_rate', 0)
        fund_data['daily_change_rate'] = history_data.get('daily_change_rate', 0)
        fund_data['fsrq'] = history_data.get('fsrq', '')
    
    return jsonify(fund_data)

@app.route('/api/fund/<fund_code>/history', methods=['GET'])
def get_fund_history(fund_code):
    """
    获取基金历史净值数据
    :param fund_code: 基金代码
    :return: 历史净值数据和近1个月涨幅
    """
    history_data = DataFetcher.get_fund_history(fund_code)
    return jsonify(history_data)

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

@app.route('/api/watchlist', methods=['GET', 'POST', 'DELETE'])
def manage_watchlist():
    """
    管理自选基金
    """
    print(f"[{datetime.now()}] 收到 /api/watchlist 请求，方法: {request.method}")
    db = next(get_db())
    try:
        if request.method == 'GET':
                # 获取自选基金列表
                watchlist = db.query(Watchlist).all()
                funds = []
                print(f"共有 {len(watchlist)} 个自选基金记录")
                
                # 收集所有自选基金的fund_code
                watchlist_fund_codes = []
                watchlist_fund_ids = set()
                
                for item in watchlist:
                    if item.fund:
                        watchlist_fund_codes.append(item.fund.fund_code)
                        watchlist_fund_ids.add(item.fund.id)
                
                print(f"开始并发获取 {len(watchlist_fund_codes)} 个自选基金的数据")
                
                # 使用批量并发方法获取所有自选基金数据
                start_time = time.time()
                funds_data_dict = get_fund_realtime_rates_batch(db, watchlist_fund_codes, force_refresh=False)
                end_time = time.time()
                print(f"批量获取自选基金数据完成，耗时: {end_time - start_time:.2f}秒")
                
                # 构建返回结果
                for item in watchlist:
                    if not item.fund:
                        continue
                    
                    fund_code = item.fund.fund_code
                    fund_data = funds_data_dict.get(fund_code)
                    
                    if fund_data:
                        fund_data['tags'] = item.tags
                        funds.append(fund_data)
                    else:
                        # 即使数据获取失败，也要返回基本信息
                        basic_fund_data = {
                            'fund_code': fund_code,
                            'fund_name': item.fund.fund_name,
                            'net_value': '',
                            'unit_net_value': '',
                            'estimate_net_value': '',
                            'estimate_change_rate': '-',
                            'estimate_time': '',
                            'one_month_rate': 0,
                            'three_month_rate': 0,
                            'one_year_rate': 0,
                            'daily_change_rate': '-',
                            'tags': item.tags
                        }
                        funds.append(basic_fund_data)
                
                # 获取持仓基金，添加不在自选列表中的持仓基金
                holdings = db.query(FundHolding).all()
                holding_fund_codes = []
                
                for holding in holdings:
                    if holding.fund.id not in watchlist_fund_ids:
                        holding_fund_codes.append(holding.fund.fund_code)
                
                # 如果有持仓基金需要获取数据，批量获取
                if holding_fund_codes:
                    print(f"开始并发获取 {len(holding_fund_codes)} 个持仓基金的数据")
                    start_time = time.time()
                    holding_funds_data_dict = get_fund_realtime_rates_batch(db, holding_fund_codes, force_refresh=False)
                    end_time = time.time()
                    print(f"批量获取持仓基金数据完成，耗时: {end_time - start_time:.2f}秒")
                    
                    # 构建持仓基金返回结果
                    for holding in holdings:
                        if holding.fund.id in watchlist_fund_ids:
                            continue
                        
                        fund_code = holding.fund.fund_code
                        fund_data = holding_funds_data_dict.get(fund_code)
                        
                        if fund_data:
                            fund_data['tags'] = ''
                            funds.append(fund_data)
                        else:
                            basic_fund_data = {
                                'fund_code': fund_code,
                                'fund_name': holding.fund.fund_name,
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
                            }
                            funds.append(basic_fund_data)
                
                print(f"返回的基金列表长度: {len(funds)}")
                return jsonify(funds)
        
        elif request.method == 'POST':
            # 添加自选基金
            data = request.json
            fund_code = data.get('fund_code')
            if not fund_code:
                return jsonify({'error': '基金代码不能为空'}), 400
            
            fund = get_or_create_fund(db, fund_code)
            if not fund:
                return jsonify({'error': '获取基金信息失败，请稍后重试'}), 400
            # 检查是否已在自选列表
            existing = db.query(Watchlist).filter(Watchlist.fund_id == fund.id).first()
            if existing:
                return jsonify({'error': '该基金已在自选列表中'}), 400
            
            # 获取标签，默认为空
            tags = data.get('tags', '')
            watchlist_item = Watchlist(fund_id=fund.id, tags=tags)
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
            # 删除自选基金
            data = request.json
            fund_code = data.get('fund_code')
            if not fund_code:
                return jsonify({'error': '基金代码不能为空'}), 400
            
            fund = db.query(Fund).filter(Fund.fund_code == fund_code).first()
            if fund:
                watchlist_item = db.query(Watchlist).filter(Watchlist.fund_id == fund.id).first()
                if watchlist_item:
                    db.delete(watchlist_item)
                    db.commit()
            return jsonify({'success': True})
    except Exception as e:
        db.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        db.close()

@app.route('/api/watchlist/tags', methods=['PUT'])
def change_fund_tags():
    """
    修改基金标签
    """
    db = next(get_db())
    try:
        data = request.json
        fund_code = data.get('fund_code')
        tags = data.get('tags', '全部')
        
        if not fund_code:
            return jsonify({'error': '基金代码不能为空'}), 400
        
        # 查找基金
        fund = db.query(Fund).filter(Fund.fund_code == fund_code).first()
        if not fund:
            return jsonify({'error': '基金不存在'}), 404
        
        # 查找自选记录
        watchlist_item = db.query(Watchlist).filter(Watchlist.fund_id == fund.id).first()
        if not watchlist_item:
            return jsonify({'error': '该基金不在自选列表中'}), 404
        
        # 更新标签
        watchlist_item.tags = tags
        db.commit()
        return jsonify({'success': True})
    except Exception as e:
        db.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        db.close()

@app.route('/api/holding', methods=['GET', 'POST'])
def manage_holding():
    """
 
    """
    import time
    db = next(get_db())
    try:
        if request.method == 'GET':
            # 获取持仓列表
            holdings = db.query(FundHolding).all()
            
            # 批量获取所有基金的实时数据（并发优化）
            fund_codes = [holding.fund.fund_code for holding in holdings]
            fund_data_dict = get_fund_realtime_rates_batch(db, fund_codes)
            
            # 批量获取所有基金的标签（板块）
            fund_ids = [holding.fund.id for holding in holdings]
            watchlist_items = db.query(Watchlist).filter(Watchlist.fund_id.in_(fund_ids)).all()
            tags_dict = {item.fund_id: item.tags for item in watchlist_items}
            
            holding_list = []
            for holding in holdings:
                fund_data = fund_data_dict.get(holding.fund.fund_code)
                tags = tags_dict.get(holding.fund.id, '')
                
                if fund_data:
                    unit_net_value = fund_data.get('unit_net_value')
                    fsrq = fund_data.get('fsrq', '')
                    daily_change_rate = fund_data.get('daily_change_rate', '-')
                    estimate_change_rate = fund_data.get('estimate_change_rate', '-')
                    
                    if unit_net_value:
                        current_value = holding.shares * float(unit_net_value)
                        
                        # 检查最新涨幅是否已更新（fsrq是否为今日）
                        import time
                        today = time.strftime('%Y-%m-%d')
                        is_today = (fsrq == today)
                        
                        if daily_change_rate != '-' and daily_change_rate != 0 and is_today:
                            # 最新涨幅已更新，使用最新涨幅计算今日收益和持仓金额
                            change_rate = float(daily_change_rate)
                            # 今日持仓金额 = 昨日持仓金额 × (1 + 涨幅%)
                            # 昨日持仓金额 = 当前持仓金额（因为单位净值是昨天的）
                            today_value = current_value * (1 + change_rate / 100)
                            estimate_profit = today_value - current_value
                            current_value = today_value
                        elif estimate_change_rate != '-':
                            # 使用估算涨幅计算今日收益
                            change_rate = float(estimate_change_rate)
                            estimate_profit = current_value - (current_value / (1 + change_rate / 100))
                        else:
                            estimate_profit = 0
                    else:
                        current_value = holding.cost
                        estimate_profit = 0
                    
                    # 实时计算持有收益和持仓金额
                    profit_loss = current_value - holding.cost
                    profit_loss_rate = (profit_loss / holding.cost * 100) if holding.cost > 0 else 0
                    
                    holding_list.append({
                        'fund_code': holding.fund.fund_code,
                        'fund_name': holding.fund.fund_name,
                        'cost': holding.cost,
                        'shares': holding.shares,
                        'avg_cost': holding.avg_cost,
                        'current_value': current_value,
                        'profit_loss': profit_loss,
                        'profit_loss_rate': profit_loss_rate,
                        'estimate_change_rate': fund_data['estimate_change_rate'],
                        'estimate_profit': estimate_profit,
                        'daily_change_rate': fund_data.get('daily_change_rate', '-'),
                        'fsrq': fund_data.get('fsrq', ''),
                        'one_month_rate': fund_data.get('one_month_rate', 0),
                        'tags': tags,
                        'platform': holding.platform or '其他'
                    })
                else:
                    holding_list.append({
                        'fund_code': holding.fund.fund_code,
                        'fund_name': holding.fund.fund_name,
                        'cost': holding.cost,
                        'shares': holding.shares,
                        'avg_cost': holding.avg_cost,
                        'current_value': holding.current_value or holding.cost,
                        'profit_loss': holding.profit_loss or 0,
                        'profit_loss_rate': holding.profit_loss_rate or 0,
                        'estimate_change_rate': '0.00',
                        'estimate_profit': 0,
                        'daily_change_rate': '-',
                        'fsrq': '',
                        'one_month_rate': 0,
                        'tags': tags,
                        'platform': holding.platform or '其他'
                    })
            return jsonify(holding_list)
        
        elif request.method == 'POST':
            # 添加或更新持仓
            data = request.json
            fund_code = data.get('fund_code')
            transaction_type = data.get('type', 'buy')  # buy: 买入, sell: 卖出, sync: 同步持仓
            tags = data.get('tags', '')
            
            if not fund_code:
                return jsonify({'error': '基金代码不能为空'}), 400
            
            # 获取或创建基金
            fund = get_or_create_fund(db, fund_code)
            
            if not fund:
                return jsonify({'error': '获取基金信息失败'}), 404
            
            # 处理标签：如果有标签，检查基金是否在自选列表中，不在则添加
            if tags:
                watchlist_item = db.query(Watchlist).filter(Watchlist.fund_id == fund.id).first()
                if not watchlist_item:
                    # 创建新的自选记录并设置标签
                    watchlist_item = Watchlist(fund_id=fund.id, tags=tags)
                    db.add(watchlist_item)
                else:
                    # 更新现有自选记录的标签
                    watchlist_item.tags = tags
            
            # 获取平台参数
            platform = data.get('platform', '其他')
            
            # 检查是否已有持仓（同时检查fund_id和platform）
            fund_holding = db.query(FundHolding).filter(
                FundHolding.fund_id == fund.id,
                FundHolding.platform == platform
            ).first()
            
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
            
            # 如果没有指定日期或无法获取指定日期的净值，使用最新净值
            if not current_price:
                fund_data = get_fund_realtime_data(db, fund_code, force_refresh=True)
                if fund_data and fund_data.get('unit_net_value'):
                    current_price = float(fund_data.get('unit_net_value'))
                    logger.info(f"使用最新净值，基金代码: {fund_code}, 净值: {current_price}, 净值日期: {fund_data.get('fsrq', '')}")
                else:
                    # 尝试从估值数据中获取
                    valuation_data = DataFetcher.get_fund_valuation(fund_code)
                    if valuation_data and valuation_data.get('estimate_net_value'):
                        current_price = float(valuation_data['estimate_net_value'])
                        logger.info(f"使用估值数据，基金代码: {fund_code}, 估值净值: {current_price}")
                    else:
                        # 如果仍然无法获取，使用1.0作为默认值
                        current_price = 1.0
                        logger.warning(f"无法获取净值数据，基金代码: {fund_code}, 使用默认值: {current_price}")
            
            if transaction_type == 'sync':
                # 同步持仓操作
                # 从前端接收current_value和profit，结合最新净值计算份额
                current_value = data.get('current_value', 0)
                profit = data.get('profit', 0)
                
                # 验证持仓金额
                if current_value <= 0:
                    return jsonify({'error': '持仓金额必须大于0'}), 400
                
                # 获取最新净值数据
                fund_data = get_fund_realtime_data(db, fund_code, force_refresh=True)
                
                unit_net_value = None
                if fund_data:
                    unit_net_value = fund_data.get('unit_net_value')
                    logger.info(f"获取基金数据成功，基金代码: {fund_code}, 净值: {unit_net_value}, 净值日期: {fund_data.get('fsrq', '')}")
                
                # 如果无法获取最新净值，使用默认值
                if not unit_net_value:
                    # 尝试从基金估值数据中获取
                    valuation_data = DataFetcher.get_fund_valuation(fund_code)
                    if valuation_data and valuation_data.get('estimate_net_value'):
                        unit_net_value = float(valuation_data['estimate_net_value'])
                        logger.info(f"使用估值数据，基金代码: {fund_code}, 估值净值: {unit_net_value}")
                    else:
                        # 如果仍然无法获取，使用1.0作为默认值
                        unit_net_value = 1.0
                        logger.warning(f"无法获取净值数据，基金代码: {fund_code}, 使用默认值: {unit_net_value}")
                else:
                    unit_net_value = float(unit_net_value)
                
                unit_net_value = float(unit_net_value)
                
                # 计算份额 = 持仓金额 / 最新净值
                shares = current_value / unit_net_value if unit_net_value > 0 else 0
                
                # 计算持仓成本：持仓金额 - 持有收益
                cost = current_value - profit
                
                # 计算平均成本
                avg_cost = cost / shares if shares > 0 else 0
                
                # 计算收益率
                profit_rate = 0
                if cost > 0:
                    profit_rate = (profit / cost) * 100
                
                logger.info(f"添加持仓 - 基金代码: {fund_code}, 平台: {platform}")
                logger.info(f"输入数据: 持仓金额={current_value}, 持有收益={profit}")
                logger.info(f"计算数据: 净值={unit_net_value}, 份额={shares}, 成本={cost}, 平均成本={avg_cost}")
                
                if fund_holding:
                    # 更新持仓
                    fund_holding.cost = cost
                    fund_holding.shares = shares
                    fund_holding.avg_cost = avg_cost
                    fund_holding.current_value = current_value
                    fund_holding.profit_loss = profit
                    fund_holding.profit_loss_rate = profit_rate
                    fund_holding.platform = platform
                else:
                    # 创建新持仓
                    fund_holding = FundHolding(
                        fund_id=fund.id,
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
                
                shares = cost / current_price
                
                if fund_holding:
                    # 更新持仓
                    total_cost = fund_holding.cost + cost
                    total_shares = fund_holding.shares + shares
                    fund_holding.cost = total_cost
                    fund_holding.shares = total_shares
                    fund_holding.avg_cost = total_cost / total_shares
                else:
                    # 创建新持仓
                    fund_holding = FundHolding(
                        fund_id=fund.id,
                        cost=cost,
                        shares=shares,
                        avg_cost=current_price
                    )
                    db.add(fund_holding)
                
                # 记录交易
                transaction = Transaction(
                    fund_id=fund.id,
                    transaction_type=transaction_type,
                    amount=cost,
                    shares=shares,
                    price=current_price
                )
                # 如果有买入日期，设置交易日期
                if buy_date:
                    from datetime import datetime
                    transaction.transaction_date = datetime.strptime(buy_date, '%Y-%m-%d')
                db.add(transaction)
                
            elif transaction_type == 'sell':
                # 卖出操作，使用前端传递的份额
                shares = data.get('shares', 0)
                sell_date = data.get('sell_date')
                
                if shares <= 0:
                    return jsonify({'error': '份额不能为空且必须大于0'}), 400
                
                if not fund_holding or fund_holding.shares < shares:
                    return jsonify({'error': '持仓份额不足'}), 400
                
                # 计算卖出金额
                amount = shares * current_price
                
                # 更新持仓
                fund_holding.cost -= amount
                fund_holding.shares -= shares
                if fund_holding.shares <= 0:
                    # 清空持仓
                    db.delete(fund_holding)
                    fund_holding = None
                else:
                    # 重新计算平均成本
                    fund_holding.avg_cost = fund_holding.cost / fund_holding.shares
                
                # 记录交易
                transaction = Transaction(
                    fund_id=fund.id,
                    transaction_type=transaction_type,
                    amount=amount,
                    shares=shares,
                    price=current_price
                )
                # 如果有卖出日期，设置交易日期
                if sell_date:
                    from datetime import datetime
                    transaction.transaction_date = datetime.strptime(sell_date, '%Y-%m-%d')
                db.add(transaction)
            
            # 计算并更新持仓信息（仅对于非同步持仓操作）
            if fund_holding and transaction_type != 'sync':
                calculate_holding(fund_holding, current_price)
            
            db.commit()
            return jsonify({'success': True})
    except Exception as e:
        db.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        db.close()

@app.route('/api/transaction/<fund_code>', methods=['GET'])
def get_transaction_history(fund_code):
    """
    获取基金交易历史
    :param fund_code: 基金代码
    :return: 交易历史列表
    """
    db = next(get_db())
    try:
        fund = db.query(Fund).filter(Fund.fund_code == fund_code).first()
        if not fund:
            return jsonify({'error': '基金不存在'}), 404
        
        transactions = db.query(Transaction).filter(Transaction.fund_id == fund.id).order_by(Transaction.transaction_date.desc()).all()
        transaction_list = []
        for transaction in transactions:
            transaction_list.append({
                'id': transaction.id,
                'type': transaction.transaction_type,
                'amount': transaction.amount,
                'shares': transaction.shares,
                'price': transaction.price,
                'date': transaction.transaction_date.strftime('%Y-%m-%d %H:%M:%S')
            })
        return jsonify(transaction_list)
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        db.close()

@app.route('/api/holding/<fund_code>/history', methods=['GET'])
def get_holding_profit_history(fund_code):
    """
    获取基金持仓收益历史记录
    :param fund_code: 基金代码
    :return: 持仓收益历史列表
    """
    db = next(get_db())
    try:
        fund = db.query(Fund).filter(Fund.fund_code == fund_code).first()
        if not fund:
            return jsonify({'error': '基金不存在'}), 404
        
        holding = db.query(FundHolding).filter(FundHolding.fund_id == fund.id).first()
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
    print(f"[{datetime.now()}] 收到 /api/test 请求")
    return jsonify({'message': '测试API正常工作', 'timestamp': datetime.now().isoformat()})

@app.route('/api/holding/<fund_code>', methods=['DELETE'])
def delete_holding(fund_code):
    """
    删除持仓
    :param fund_code: 基金代码
    :return: 删除结果
    """
    db = next(get_db())
    try:
        fund = db.query(Fund).filter(Fund.fund_code == fund_code).first()
        if not fund:
            return jsonify({'error': '基金不存在'}), 404
        
        fund_holding = db.query(FundHolding).filter(FundHolding.fund_id == fund.id).first()
        if not fund_holding:
            return jsonify({'error': '持仓不存在'}), 404
        
        db.delete(fund_holding)
        db.commit()
        return jsonify({'success': True})
    except Exception as e:
        db.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        db.close()

@app.route('/api/holding/<fund_code>', methods=['PUT'])
@retry_db_operation()
def update_holding(fund_code):
    """
    更新持仓信息
    :param fund_code: 基金代码
    :return: 更新结果
    """
    db = next(get_db())
    try:
        data = request.json
        current_value = data.get('current_value', 0)
        profit = data.get('profit', 0)
        platform = data.get('platform', '其他')
        
        if current_value <= 0:
            return jsonify({'error': '持仓金额不能为空且必须大于0'}), 400
        
        # 获取基金
        fund = db.query(Fund).filter(Fund.fund_code == fund_code).first()
        if not fund:
            return jsonify({'error': '基金不存在'}), 404
        
        # 获取最新净值数据
        fund_data = get_fund_realtime_data(db, fund_code, force_refresh=True, need_history_data=False, skip_db_write=True)
        if not fund_data:
            return jsonify({'error': '获取基金数据失败'}), 404
        
        unit_net_value = fund_data.get('unit_net_value')
        if not unit_net_value:
            return jsonify({'error': '无法获取最新净值'}), 404
        
        unit_net_value = float(unit_net_value)
        
        # 计算份额 = 持仓金额 / 最新净值
        shares = current_value / unit_net_value if unit_net_value > 0 else 0
        
        # 计算持仓成本：持仓金额 - 持有收益
        cost = current_value - profit
        
        # 计算平均成本
        avg_cost = cost / shares if shares > 0 else 0
        # 计算收益率
        profit_rate = 0
        if cost > 0:
            profit_rate = (profit / cost) * 100
        
        # 检查是否已有持仓（同时检查fund_id和platform）
        fund_holding = db.query(FundHolding).filter(
            FundHolding.fund_id == fund.id,
            FundHolding.platform == platform
        ).first()
        if not fund_holding:
            logger.warning(f"持仓不存在，基金ID: {fund.id}, 平台: {platform}")
            return jsonify({'error': '持仓不存在'}), 404
        
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
def update_watchlist_tags():
    """
    更新自选基金的板块标签
    """
    db = next(get_db())
    try:
        data = request.json
        fund_code = data.get('fund_code')
        tags = data.get('tags', '')
        
        if not fund_code:
            return jsonify({'error': '基金代码不能为空'}), 400
        
        # 获取基金
        fund = db.query(Fund).filter(Fund.fund_code == fund_code).first()
        if not fund:
            return jsonify({'error': '基金不存在'}), 404
        
        # 检查是否在自选列表中
        watchlist_item = db.query(Watchlist).filter(Watchlist.fund_id == fund.id).first()
        if not watchlist_item:
            # 如果不在自选列表中，创建新记录
            watchlist_item = Watchlist(fund_id=fund.id, tags=tags)
            db.add(watchlist_item)
        else:
            # 更新现有记录的标签
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
def update_holding_tags():
    """
    更新持仓基金的板块标签
    """
    db = next(get_db())
    try:
        data = request.json
        fund_code = data.get('fund_code')
        tags = data.get('tags', '')
        
        if not fund_code:
            return jsonify({'error': '基金代码不能为空'}), 400
        
        # 获取基金
        fund = db.query(Fund).filter(Fund.fund_code == fund_code).first()
        if not fund:
            return jsonify({'error': '基金不存在'}), 404
        
        # 检查是否在自选列表中（因为持仓的标签是从自选列表中获取的）
        watchlist_item = db.query(Watchlist).filter(Watchlist.fund_id == fund.id).first()
        if not watchlist_item:
            # 如果不在自选列表中，创建新记录
            watchlist_item = Watchlist(fund_id=fund.id, tags=tags)
            db.add(watchlist_item)
        else:
            # 更新现有记录的标签
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

@app.route('/api/platform', methods=['GET'])
def get_platforms():
    """
    获取平台列表
    """
    db = next(get_db())
    try:
        platforms = db.query(Platform).order_by(Platform.order, Platform.id).all()
        platform_list = [{'id': p.id, 'name': p.name} for p in platforms]
        return jsonify(platform_list)
    except Exception as e:
        db.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        db.close()

@app.route('/api/platform', methods=['POST'])
def add_platform():
    """
    添加平台
    """
    data = request.json
    name = data.get('name')
    if not name:
        return jsonify({'error': '平台名称不能为空'}), 400
    
    db = next(get_db())
    try:
        # 检查平台是否已存在
        existing = db.query(Platform).filter(Platform.name == name).first()
        if existing:
            return jsonify({'error': '平台已存在'}), 400
        
        # 获取当前最大的order值
        max_order = db.query(Platform).with_entities(func.max(Platform.order)).scalar() or 0
        
        platform = Platform(name=name, order=max_order + 1)
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
def update_platform(platform_id):
    """
    更新平台
    """
    db = next(get_db())
    try:
        data = request.json
        name = data.get('name', '').strip()
        
        if not name:
            return jsonify({'error': '平台名称不能为空'}), 400
        
        # 获取平台
        platform = db.query(Platform).filter(Platform.id == platform_id).first()
        if not platform:
            return jsonify({'error': '平台不存在'}), 404
        
        # 检查新名称是否与其他平台冲突
        existing = db.query(Platform).filter(Platform.name == name, Platform.id != platform_id).first()
        if existing:
            return jsonify({'error': '平台名称已存在'}), 400
        
        # 更新平台
        platform.name = name
        db.commit()
        
        return jsonify({'success': True})
    except Exception as e:
        db.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        db.close()

@app.route('/api/platform/<int:platform_id>', methods=['DELETE'])
def delete_platform(platform_id):
    """
    删除平台
    """
    db = next(get_db())
    try:
        platform = db.query(Platform).filter(Platform.id == platform_id).first()
        if not platform:
            return jsonify({'error': '平台不存在'}), 404
        
        # 检查是否有持仓使用该平台
        holdings = db.query(FundHolding).filter(FundHolding.platform == platform.name).all()
        if holdings:
            return jsonify({'error': f'该平台下有{len(holdings)}个持仓，无法删除'}), 400
        
        db.delete(platform)
        db.commit()
        return jsonify({'success': True})
    except Exception as e:
        db.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        db.close()

@app.route('/api/platform/order', methods=['PUT'])
def update_platform_order():
    """
    更新平台排序
    """
    data = request.json
    order_data = data.get('order', [])
    
    if not order_data:
        return jsonify({'error': '排序数据不能为空'}), 400
    
    db = next(get_db())
    try:
        for item in order_data:
            platform_id = item.get('id')
            order = item.get('order')
            
            if platform_id and order is not None:
                platform = db.query(Platform).filter(Platform.id == platform_id).first()
                if platform:
                    platform.order = order
        
        db.commit()
        return jsonify({'success': True})
    except Exception as e:
        db.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        db.close()

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
