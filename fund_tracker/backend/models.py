from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Boolean, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from config import DATABASE_URL, SQLITE_CONNECT_ARGS
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

Base = declarative_base()
engine = create_engine(DATABASE_URL, echo=False, connect_args=SQLITE_CONNECT_ARGS)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

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
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # 关系
    fund = relationship("Fund", back_populates="realtime_data")

class FundHolding(Base):
    """基金持仓表"""
    __tablename__ = 'fund_holding'
    
    id = Column(Integer, primary_key=True, index=True)
    fund_id = Column(Integer, ForeignKey('fund.id'), nullable=False)
    cost = Column(Float, nullable=False)  # 持仓成本
    shares = Column(Float, nullable=False)  # 持仓份额
    avg_cost = Column(Float, nullable=False)  # 平均成本
    current_value = Column(Float)  # 当前价值（持仓金额）
    profit_loss = Column(Float)  # 盈亏金额
    profit_loss_rate = Column(Float)  # 盈亏比例
    platform = Column(String(50), default='其他')  # 平台（如：支付宝、理财通等）
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # 关系
    fund = relationship("Fund", back_populates="holdings")

class Transaction(Base):
    """交易记录表"""
    __tablename__ = 'transaction'
    
    id = Column(Integer, primary_key=True, index=True)
    fund_id = Column(Integer, ForeignKey('fund.id'), nullable=False)
    transaction_type = Column(String(10), nullable=False)  # buy: 买入, sell: 卖出
    amount = Column(Float, nullable=False)  # 交易金额
    shares = Column(Float, nullable=False)  # 交易份额
    price = Column(Float, nullable=False)  # 交易价格
    transaction_date = Column(DateTime(timezone=True), server_default=func.now())
    
    # 关系
    fund = relationship("Fund", back_populates="transactions")

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
    """自选基金表"""
    __tablename__ = 'watchlist'
    
    id = Column(Integer, primary_key=True, index=True)
    fund_id = Column(Integer, ForeignKey('fund.id'), unique=True, nullable=False)
    tags = Column(String(255), default='')  # 标签列表，逗号分隔，默认为空
    added_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # 关系
    fund = relationship("Fund", back_populates="watchlist")

class Platform(Base):
    """平台表"""
    __tablename__ = 'platform'
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(50), unique=True, nullable=False)  # 平台名称，如：支付宝、理财通
    order = Column(Integer, default=0)  # 排序顺序
    created_at = Column(DateTime(timezone=True), server_default=func.now())

# 创建表
def create_tables():
    Base.metadata.create_all(bind=engine)

# 获取数据库会话
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
