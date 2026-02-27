from app import get_db, get_fund_realtime_data
from models import FundHolding, HoldingProfitHistory
from datetime import datetime

db = next(get_db())
try:
    # 获取所有持仓基金
    holdings = db.query(FundHolding).all()
    
    print(f"找到 {len(holdings)} 个持仓基金\n")
    
    for holding in holdings:
        fund_code = holding.fund.fund_code
        
        print(f"处理基金: {fund_code} - {holding.fund.fund_name}")
        print(f"  当前持仓成本: {holding.cost:.2f}")
        print(f"  当前份额: {holding.shares}")
        print(f"  当前价值: {holding.current_value:.2f}")
        print(f"  当前盈亏: {holding.profit_loss:.2f} ({holding.profit_loss_rate:.2f}%)")
        
        # 获取基金实时数据（强制刷新）
        fund_data = get_fund_realtime_data(db, fund_code, force_refresh=True)
        
        if not fund_data:
            print(f"  ❌ 数据获取失败，跳过\n")
            continue
        
        # 显示获取到的数据
        print(f"  净值日期: {fund_data.get('fsrq', '')}")
        print(f"  单位净值: {fund_data.get('unit_net_value', 'N/A')}")
        print(f"  日涨跌幅: {fund_data.get('daily_change_rate', 'N/A')}%")
        
        # 检查单位净值
        unit_net_value = fund_data.get('unit_net_value')
        if not unit_net_value:
            print(f"  ❌ 单位净值未获取到，跳过\n")
            continue
        
        # 计算新的当前价值
        new_current_value = holding.shares * float(unit_net_value)
        new_profit_loss = new_current_value - holding.cost
        new_profit_loss_rate = (new_profit_loss / holding.cost) * 100 if holding.cost > 0 else 0
        
        print(f"  新的当前价值: {new_current_value:.2f}")
        print(f"  新的盈亏: {new_profit_loss:.2f} ({new_profit_loss_rate:.2f}%)")
        
        # 更新数据库
        old_current_value = holding.current_value
        old_profit_loss = holding.profit_loss
        old_profit_loss_rate = holding.profit_loss_rate
        
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
            fsrq=fund_data.get('fsrq', ''),
            daily_change_rate=float(fund_data.get('daily_change_rate', 0)) if fund_data.get('daily_change_rate') != '-' else 0
        )
        db.add(history_record)
        
        print(f"  ✅ 持仓收益已更新")
        print(f"  📊 变化: 价值 {old_current_value:.2f} → {new_current_value:.2f}, 盈亏 {old_profit_loss:.2f} → {new_profit_loss:.2f}\n")
    
    db.commit()
    print("=" * 60)
    print("所有持仓基金更新完成！")
    print("=" * 60)
    
except Exception as e:
    db.rollback()
    print(f"❌ 更新失败: {e}")
    import traceback
    traceback.print_exc()
finally:
    db.close()
