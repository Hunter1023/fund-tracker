import sqlite3
import shutil
import os
from datetime import datetime

# 创建数据库备份
timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
backup_file = f'fund_tracker_backup_{timestamp}.db'
print(f'正在创建数据库备份: {backup_file}')
shutil.copy2('fund_tracker.db', backup_file)
print('备份完成\n')

# 连接数据库
conn = sqlite3.connect('fund_tracker.db')
c = conn.cursor()

print('开始数据库迁移...')

# 1. 为 fund_realtime_data 表添加 daily_change_rate 字段
print('1. 为 fund_realtime_data 表添加 daily_change_rate 字段')
c.execute('ALTER TABLE fund_realtime_data ADD COLUMN daily_change_rate FLOAT DEFAULT 0')

# 2. 为 holding_profit_history 表添加 daily_change_rate 字段
print('2. 为 holding_profit_history 表添加 daily_change_rate 字段')
c.execute('ALTER TABLE holding_profit_history ADD COLUMN daily_change_rate FLOAT DEFAULT 0')

# 3. 复制 fund_realtime_data 表的数据
print('3. 复制 fund_realtime_data 表的数据')
c.execute('UPDATE fund_realtime_data SET daily_change_rate = yesterday_change_rate WHERE yesterday_change_rate IS NOT NULL')

# 4. 复制 holding_profit_history 表的数据
print('4. 复制 holding_profit_history 表的数据')
c.execute('UPDATE holding_profit_history SET daily_change_rate = yesterday_change_rate WHERE yesterday_change_rate IS NOT NULL')

# 5. 重新创建 fund_realtime_data 表（不带旧字段）
print('5. 重建 fund_realtime_data 表')
c.execute('''
CREATE TABLE fund_realtime_data_new AS
SELECT 
    id, fund_id, net_value_date, unit_net_value, 
    estimate_net_value, estimate_change_rate, estimate_time, 
    one_month_rate, three_month_rate, one_year_rate, 
    daily_change_rate, fsrq, net_values, updated_at
FROM fund_realtime_data
''')
c.execute('DROP TABLE fund_realtime_data')
c.execute('ALTER TABLE fund_realtime_data_new RENAME TO fund_realtime_data')

# 6. 重新创建 holding_profit_history 表（不带旧字段）
print('6. 重建 holding_profit_history 表')
c.execute('''
CREATE TABLE holding_profit_history_new AS
SELECT 
    id, holding_id, fund_code, cost, shares, 
    avg_cost, current_value, profit_loss, profit_loss_rate, 
    unit_net_value, fsrq, daily_change_rate, recorded_at
FROM holding_profit_history
''')
c.execute('DROP TABLE holding_profit_history')
c.execute('ALTER TABLE holding_profit_history_new RENAME TO holding_profit_history')

# 提交更改
conn.commit()
print('\n数据库迁移完成!')
print('新字段: daily_change_rate')
print('旧字段: yesterday_change_rate (已删除)')
print(f'数据库备份文件: {backup_file}')

# 验证结果
print('\n验证迁移结果:')
print('fund_realtime_data 表结构:')
c.execute('PRAGMA table_info(fund_realtime_data)')
for row in c.fetchall():
    print(row)

print('\nholding_profit_history 表结构:')
c.execute('PRAGMA table_info(holding_profit_history)')
for row in c.fetchall():
    print(row)

conn.close()