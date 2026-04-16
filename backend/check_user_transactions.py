from app import get_db
from models import User, Transaction, Fund

db = next(get_db())
try:
    # 查找用户
    user = db.query(User).filter(User.email == 'hspecial@163.com').first()
    print(f'User: {user}')
    if user:
        print(f'User ID: {user.id}')
        
        # 查找基金
        fund = db.query(Fund).filter(Fund.fund_code == '020111').first()
        if fund:
            print(f'Fund ID: {fund.id}')
            
            # 查找交易记录
            transactions = db.query(Transaction).filter(
                Transaction.user_id == user.id,
                Transaction.fund_id == fund.id
            ).all()
            print(f'Transactions count: {len(transactions)}')
            for t in transactions:
                print(f'Transaction: {t.id}, type: {t.transaction_type}, date: {t.transaction_date}, amount: {t.amount}, platform_id: {t.platform_id}')
        else:
            print('Fund not found')
    else:
        print('User not found')
finally:
    db.close()