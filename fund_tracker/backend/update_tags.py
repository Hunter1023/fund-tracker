from models import SessionLocal, Watchlist

# 获取数据库会话
db = SessionLocal()

try:
    # 查询所有Watchlist记录
    watchlist_items = db.query(Watchlist).all()
    
    # 统计更新的记录数
    updated_count = 0
    
    # 遍历所有记录
    for item in watchlist_items:
        # 检查tags是否为"全部"或其变体
        if item.tags in ['全部', '全 部', ' 全部', '全部 ']:
            # 将tags设置为空字符串
            item.tags = ''
            updated_count += 1
    
    # 提交更改
    db.commit()
    
    # 打印更新结果
    print(f"更新完成！共更新了 {updated_count} 条记录")
    
    # 验证更新结果
    print("更新后的记录:")
    for item in db.query(Watchlist).all():
        print(f"{item.fund.fund_name}: {item.tags}")
        
finally:
    # 关闭数据库会话
    db.close()