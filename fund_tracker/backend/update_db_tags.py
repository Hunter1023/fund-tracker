import sqlite3

# 连接到SQLite数据库
conn = sqlite3.connect('fund_tracker.db')
cursor = conn.cursor()

try:
    # 检查watchlist表是否存在group_name列
    cursor.execute("PRAGMA table_info(watchlist)")
    columns = [column[1] for column in cursor.fetchall()]
    
    tags_exists = 'tags' in columns
    group_name_exists = 'group_name' in columns
    
    if not tags_exists:
        # 添加tags列
        cursor.execute("ALTER TABLE watchlist ADD COLUMN tags TEXT DEFAULT '全部'")
        print('已添加tags列，默认值为"全部"')
        tags_exists = True
    
    if group_name_exists:
        # 将group_name列的数据迁移到tags列
        cursor.execute("UPDATE watchlist SET tags = group_name WHERE group_name IS NOT NULL")
        print(f'已迁移 {cursor.rowcount} 条记录，将group_name数据迁移到tags列')
        
        # 验证迁移结果
        cursor.execute("SELECT DISTINCT tags FROM watchlist")
        tags = cursor.fetchall()
        print('当前存在的标签:', [tag[0] for tag in tags])
    else:
        print('group_name列不存在，跳过迁移')
    
    # 查看当前数据
    cursor.execute("SELECT COUNT(*) FROM watchlist")
    count = cursor.fetchone()[0]
    print(f'当前自选基金数量: {count}')
    
finally:
    # 提交更改并关闭连接
    conn.commit()
    conn.close()