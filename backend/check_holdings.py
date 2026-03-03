import sqlite3
import os

# 连接数据库
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
db_path = os.path.join(BASE_DIR, '..', 'data', 'fund_tracker.db')
conn = sqlite3.connect(db_path)
c = conn.cursor()

print('开始检查数据库中的持仓记录...')

# 查看当前所有持仓
print('\n当前所有持仓:')
c.execute('''
    SELECT fh.id, f.fund_code, f.fund_name, fh.platform, fh.current_value, fh.cost
    FROM fund_holding fh
    JOIN fund f ON fh.fund_id = f.id
    ORDER BY fh.id
''')
for row in c.fetchall():
    print(f'ID: {row[0]}, 基金: {row[1]} ({row[2]}), 平台: {row[3]}, 金额: {row[4]}, 成本: {row[5]}')

# 检查是否有重复的基金在不同平台
print('\n检查同一基金在不同平台的持仓:')
c.execute('''
    SELECT f.fund_code, f.fund_name, COUNT(*) as count
    FROM fund_holding fh
    JOIN fund f ON fh.fund_id = f.id
    GROUP BY f.fund_code, f.fund_name
    HAVING COUNT(*) > 1
''')
duplicates = c.fetchall()
if duplicates:
    print('发现同一基金在不同平台的持仓:')
    for row in duplicates:
        print(f'基金: {row[0]} ({row[1]}), 持仓数量: {row[2]}')
else:
    print('没有发现同一基金在不同平台的持仓')

conn.close()
print('\n检查完成!')