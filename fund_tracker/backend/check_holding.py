import sqlite3
import os

# 数据库文件路径
db_path = os.path.join(os.path.dirname(__file__), 'fund_tracker.db')

print(f"检查数据库: {db_path}")
print(f"数据库是否存在: {os.path.exists(db_path)}")

if os.path.exists(db_path):
    # 连接数据库
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # 检查 fund 表
    print("\n=== 检查 fund 表 ===")
    cursor.execute("SELECT id, fund_code, fund_name FROM fund WHERE fund_code = '017470'")
    fund_result = cursor.fetchall()
    print(f"基金 017470 记录: {fund_result}")
    
    if fund_result:
        fund_id = fund_result[0][0]
        
        # 检查 fund_holding 表
        print("\n=== 检查 fund_holding 表 ===")
        cursor.execute("SELECT id, fund_id, cost, shares, avg_cost, current_value, profit_loss, profit_loss_rate, platform FROM fund_holding WHERE fund_id = ?", (fund_id,))
        holding_results = cursor.fetchall()
        print(f"持仓记录数量: {len(holding_results)}")
        
        for holding in holding_results:
            print(f"持仓ID: {holding[0]}, 基金ID: {holding[1]}, 成本: {holding[2]}, 份额: {holding[3]}, 平均成本: {holding[4]}, 当前价值: {holding[5]}, 持有收益: {holding[6]}, 收益率: {holding[7]}, 平台: {holding[8]}")
    
    # 检查 platform 表
    print("\n=== 检查 platform 表 ===")
    cursor.execute("SELECT * FROM platform")
    platform_results = cursor.fetchall()
    print(f"平台记录: {platform_results}")
    
    # 关闭连接
    conn.close()
else:
    print("数据库文件不存在")