from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Boolean, Text, UniqueConstraint
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from config import DATABASE_URL, CONNECT_ARGS
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import uuid

Base = declarative_base()

try:
    engine = create_engine(DATABASE_URL, echo=False, connect_args=CONNECT_ARGS)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    print("数据库连接成功")
except Exception as e:
    print(f"数据库连接失败: {e}")

    class MockEngine:
        def execute(self, *args, **kwargs):
            pass

    class MockSession:
        def query(self, *args, **kwargs):
            class MockQuery:
                def filter(self, *args, **kwargs):
                    return self
                def first(self):
                    return None
                def all(self):
                    return []
                def count(self):
                    return 0
                def order_by(self, *args, **kwargs):
                    return self
                def in_(self, *args, **kwargs):
                    return self
            return MockQuery()
        def add(self, *args, **kwargs):
            pass
        def commit(self):
            pass
        def rollback(self):
            pass
        def flush(self):
            pass
        def refresh(self, *args, **kwargs):
            pass
        def close(self):
            pass

    engine = MockEngine()
    SessionLocal = lambda: MockSession()
    print("使用模拟数据库会话，应用程序将继续运行")


class User(Base):
    __tablename__ = 'user'

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, nullable=True, index=True)
    username = Column(String(100), unique=True, nullable=True, index=True)
    password_hash = Column(String(255), nullable=True)
    github_id = Column(String(100), unique=True, nullable=True, index=True)
    github_username = Column(String(100), nullable=True)
    github_avatar = Column(String(500), nullable=True)
    nickname = Column(String(100), nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    holdings = relationship("FundHolding", back_populates="user")
    watchlist = relationship("Watchlist", back_populates="user")
    transactions = relationship("Transaction", back_populates="user")
    platforms = relationship("Platform", back_populates="user")

class Fund(Base):
    """基金信息表"""
    __tablename__ = 'fund'

    id = Column(Integer, primary_key=True, index=True)
    fund_code = Column(String(10), unique=True, nullable=False, index=True)
    fund_name = Column(String(100), nullable=False)
    fund_type = Column(String(50))
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # 关系
    holdings = relationship("FundHolding", back_populates="fund")
    transactions = relationship("Transaction", back_populates="fund")
    watchlist = relationship("Watchlist", back_populates="fund", uselist=False)
    realtime_data = relationship("FundRealtimeData", back_populates="fund", uselist=False)

class FundRealtimeData(Base):
    """基金实时数据表"""
    __tablename__ = 'fund_realtime_data'

    id = Column(Integer, primary_key=True, index=True)
    fund_id = Column(Integer, ForeignKey('fund.id'), unique=True, nullable=False)

    # 估值数据
    net_value_date = Column(String(20))  # 净值日期
    unit_net_value = Column(Float)  # 单位净值
    estimate_net_value = Column(Float)  # 估算净值
    estimate_change_rate = Column(Float)  # 估算涨跌幅
    estimate_time = Column(String(50))  # 估值时间

    # 历史涨跌幅数据
    one_month_rate = Column(Float, default=0)  # 近1月收益率
    three_month_rate = Column(Float, default=0)  # 近3月收益率
    one_year_rate = Column(Float, default=0)  # 近1年收益率
    daily_change_rate = Column(Float, default=0)  # 日涨跌幅
    fsrq = Column(String(20))  # 净值日期

    # 历史净值数据（JSON格式存储）
    net_values = Column(Text)  # 历史净值数据，JSON格式

    # 更新时间
    updated_at = Column(DateTime(timezone=False), server_default=func.now(), onupdate=func.now())

    # 关系
    fund = relationship("Fund", back_populates="realtime_data")

class FundHolding(Base):
    __tablename__ = 'fund_holding'

    id = Column(Integer, primary_key=True, index=True)
    fund_id = Column(Integer, ForeignKey('fund.id'), nullable=False)
    user_id = Column(Integer, ForeignKey('user.id'), nullable=True, index=True)
    cost = Column(Float, nullable=False)
    shares = Column(Float, nullable=False)
    avg_cost = Column(Float, nullable=False)
    current_value = Column(Float)
    profit_loss = Column(Float)
    profit_loss_rate = Column(Float)
    platform = Column(String(50), default='其他')
    updated_at = Column(DateTime(timezone=False), server_default=func.now(), onupdate=func.now())

    fund = relationship("Fund", back_populates="holdings")
    user = relationship("User", back_populates="holdings")
    profit_histories = relationship("HoldingProfitHistory", backref="holding", cascade="all, delete-orphan")

class Transaction(Base):
    __tablename__ = 'transaction'

    id = Column(Integer, primary_key=True, index=True)
    fund_id = Column(Integer, ForeignKey('fund.id'), nullable=False)
    user_id = Column(Integer, ForeignKey('user.id'), nullable=True, index=True)
    platform_id = Column(Integer, ForeignKey('platform.id'), nullable=True)
    transaction_type = Column(String(10), nullable=False)
    amount = Column(Float, nullable=False)
    shares = Column(Float, nullable=False)
    price = Column(Float, nullable=False)
    transaction_date = Column(DateTime(timezone=True), server_default=func.now())

    fund = relationship("Fund", back_populates="transactions")
    user = relationship("User", back_populates="transactions")

class HoldingProfitHistory(Base):
    """持仓收益历史记录表"""
    __tablename__ = 'holding_profit_history'

    id = Column(Integer, primary_key=True, index=True)
    holding_id = Column(Integer, ForeignKey('fund_holding.id'), nullable=False)
    fund_code = Column(String(10), nullable=False, index=True)  # 基金代码，便于查询

    # 持仓数据快照
    cost = Column(Float, nullable=False)  # 持仓成本
    shares = Column(Float, nullable=False)  # 持仓份额
    avg_cost = Column(Float, nullable=False)  # 平均成本
    current_value = Column(Float, nullable=False)  # 当前价值
    profit_loss = Column(Float, nullable=False)  # 盈亏金额
    profit_loss_rate = Column(Float, nullable=False)  # 盈亏比例

    # 基金数据快照
    unit_net_value = Column(Float, nullable=False)  # 单位净值
    fsrq = Column(String(20), nullable=False)  # 净值日期
    daily_change_rate = Column(Float, nullable=False)  # 日涨跌幅

    # 记录时间
    recorded_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)

class Watchlist(Base):
    __tablename__ = 'watchlist'

    id = Column(Integer, primary_key=True, index=True)
    fund_id = Column(Integer, ForeignKey('fund.id'), nullable=False)
    user_id = Column(Integer, ForeignKey('user.id'), nullable=True, index=True)
    tags = Column(String(255), default='')
    added_at = Column(DateTime(timezone=True), server_default=func.now())

    fund = relationship("Fund", back_populates="watchlist")
    user = relationship("User", back_populates="watchlist")

    __table_args__ = (
        UniqueConstraint('fund_id', 'user_id', name='uq_watchlist_fund_user'),
    )

class Platform(Base):
    __tablename__ = 'platform'

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(50), nullable=False)
    user_id = Column(Integer, ForeignKey('user.id'), nullable=True, index=True)
    order_num = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="platforms")

    __table_args__ = (
        UniqueConstraint('name', 'user_id', name='uq_platform_name_user'),
    )

# 创建表
def migrate_add_user_columns():
    with engine.connect() as conn:
        result = conn.execute(
            __import__('sqlalchemy').text(
                "SELECT column_name FROM information_schema.columns WHERE table_name = 'user'"
            )
        )
        user_table_exists = result.rowcount > 0

        if not user_table_exists:
            print("迁移: user 表不存在，将由 create_tables 创建")
            return

        tables_user_id = {
            'watchlist': 'user_id',
            'fund_holding': 'user_id',
            'transaction': 'user_id',
            'platform': 'user_id',
        }

        for table, column in tables_user_id.items():
            try:
                result = conn.execute(
                    __import__('sqlalchemy').text(
                        f"SELECT column_name FROM information_schema.columns "
                        f"WHERE table_name = '{table}' AND column_name = '{column}'"
                    )
                )
                if result.rowcount == 0:
                    conn.execute(
                        __import__('sqlalchemy').text(
                            f"ALTER TABLE {table} ADD COLUMN {column} INTEGER REFERENCES \"user\"(id)"
                        )
                    )
                    conn.commit()
                    print(f"迁移: 已为 {table} 表添加 {column} 列")
            except Exception as e:
                print(f"迁移: {table}.{column} 跳过 ({e})")


def create_tables():
    try:
        migrate_add_user_columns()
        Base.metadata.create_all(bind=engine)
        print("数据库表创建成功")
    except Exception as e:
        print(f"数据库表创建失败: {e}")

# 获取数据库会话
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        if hasattr(db, 'close'):
            db.close()
