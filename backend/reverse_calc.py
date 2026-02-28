from app import get_db, get_fund_realtime_data

db = next(get_db())
from models import FundHolding, Fund

fund_code = '021986'
holding = db.query(FundHolding).join(Fund).filter(Fund.fund_code == fund_code).first()

if holding:
    print(f"基金代码: {fund_code}")
    print(f"份额: {holding.shares}")
    print(f"持仓成本: {holding.cost}")
    print(f"当前价值: {holding.current_value}")
    print(f"持有收益: {holding.profit_loss}")
    
    # 获取最新数据
    fund_data = get_fund_realtime_data(db, fund_code, force_refresh=True)
    daily_change_rate = float(fund_data.get('daily_change_rate', 0))
    unit_net_value = float(fund_data.get('unit_net_value', 0))
    
    print(f"\n最新数据:")
    print(f"单位净值: {unit_net_value}")
    print(f"最新涨幅: {daily_change_rate}%")
    
    # 反推：如果持有收益是-245.24元，当前价值应该是多少？
    target_profit = -245.24
    target_current_value = holding.cost + target_profit
    print(f"\n反推计算:")
    print(f"如果持有收益是{target_profit}元，当前价值应该是: {target_current_value}元")
    
    # 基于最新涨幅计算
    new_current_value = target_current_value * (1 + daily_change_rate / 100)
    new_profit = new_current_value - holding.cost
    print(f"基于最新涨幅{daily_change_rate}%计算:")
    print(f"新的当前价值 = {target_current_value} × (1 + {daily_change_rate}/100) = {new_current_value}")
    print(f"新的持有收益 = {new_current_value} - {holding.cost} = {new_profit}")
    
    # 正确的计算方式
    correct_current_value = holding.shares * unit_net_value
    correct_profit = correct_current_value - holding.cost
    print(f"\n正确的计算方式（份额 × 单位净值）:")
    print(f"当前价值 = {holding.shares} × {unit_net_value} = {correct_current_value}")
    print(f"持有收益 = {correct_current_value} - {holding.cost} = {correct_profit}")

db.close()