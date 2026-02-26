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

# 为 fund_holding 表添加 platform 字段
print('为 fund_holding 表添加 platform 字段')
c.execute('ALTER TABLE fund_holding ADD COLUMN platform TEXT DEFAULT \'其他\'')

# 提交更改
conn.commit()
print('\n数据库迁移完成!')
print('新字段: platform (默认值: "其他")')
print(f'数据库备份文件: {backup_file}')

# 验证结果
print('\n验证迁移结果:')
print('fund_holding 表结构:')
c.execute('PRAGMA table_info(fund_holding)')
for row in c.fetchall():
    print(row)

conn.close()