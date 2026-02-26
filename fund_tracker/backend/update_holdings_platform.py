import sqlite3
from datetime import datetime

# 连接数据库
conn = sqlite3.connect('fund_tracker.db')
c = conn.cursor()

print('开始批量更新持仓平台...')

# 更新所有持仓的平台为"支付宝"
c.execute('UPDATE fund_holding SET platform = ? WHERE platform IS NULL OR platform = ?', ('支付宝', '其他'))

# 获取更新的数量
updated_count = c.rowcount

conn.commit()
print(f'已更新 {updated_count} 个持仓的平台为"支付宝"')

# 验证结果
print('\n验证更新结果:')
c.execute('SELECT platform, COUNT(*) as count FROM fund_holding GROUP BY platform')
for row in c.fetchall():
    print(f'平台: {row[0]}, 数量: {row[1]}')

conn.close()
print('\n更新完成!')