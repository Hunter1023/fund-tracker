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

# 创建 platform 表
print('创建 platform 表')
c.execute('''
CREATE TABLE IF NOT EXISTS platform (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
)
''')

# 插入默认平台数据
print('插入默认平台数据')
default_platforms = ['支付宝', '理财通', '天天基金', '其他']
for platform_name in default_platforms:
    try:
        c.execute('INSERT INTO platform (name) VALUES (?)', (platform_name,))
    except sqlite3.IntegrityError:
        print(f'平台 "{platform_name}" 已存在，跳过')

# 提交更改
conn.commit()
print('\n数据库迁移完成!')
print('新表: platform')
print('默认平台: 支付宝、理财通、天天基金、其他')
print(f'数据库备份文件: {backup_file}')

# 验证结果
print('\n验证迁移结果:')
print('platform 表数据:')
c.execute('SELECT * FROM platform')
for row in c.fetchall():
    print(row)

conn.close()