import sqlite3

# 连接到SQLite数据库
conn = sqlite3.connect('fund_tracker.db')
cursor = conn.cursor()

try:
    # 将所有分组名称从"默认"改为"全部"
    cursor.execute("UPDATE watchlist SET group_name = '全部' WHERE group_name = '默认'")
    print(f'已更新 {cursor.rowcount} 条记录，将分组名称从"默认"改为"全部"')
    
    # 查看更新后的结果
    cursor.execute("SELECT DISTINCT group_name FROM watchlist")
    groups = cursor.fetchall()
    print('当前存在的分组:', [group[0] for group in groups])
    
finally:
    # 提交更改并关闭连接
    conn.commit()
    conn.close()