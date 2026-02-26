import sqlite3

# 连接到SQLite数据库
conn = sqlite3.connect('fund_tracker.db')
cursor = conn.cursor()

try:
    # 检查watchlist表是否存在group_name列
    cursor.execute("PRAGMA table_info(watchlist)")
    columns = [column[1] for column in cursor.fetchall()]
    
    if 'group_name' not in columns:
        # 添加group_name列，默认值为'默认'
        cursor.execute("ALTER TABLE watchlist ADD COLUMN group_name TEXT DEFAULT '默认'")
        print('已添加group_name列，默认值为"默认"')
    else:
        print('group_name列已存在')
    
    # 查看watchlist表中的数据
    cursor.execute("SELECT * FROM watchlist")
    watchlist_data = cursor.fetchall()
    print('自选基金数量:', len(watchlist_data))
    
    # 查看fund表中的数据
    cursor.execute("SELECT * FROM fund")
    fund_data = cursor.fetchall()
    print('基金数量:', len(fund_data))
    
finally:
    # 提交更改并关闭连接
    conn.commit()
    conn.close()