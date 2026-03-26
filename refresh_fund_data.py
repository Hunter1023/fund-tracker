import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))

from app import get_db
from app import get_fund_realtime_data

db = next(get_db())
try:
    print("开始刷新基金 013841 的数据...")
    result = get_fund_realtime_data(db, '013841', force_refresh=True, need_history_data=True)
    print("刷新完成！")
    if result:
        print("成功获取数据")
    else:
        print("未获取到数据")
finally:
    db.close()
