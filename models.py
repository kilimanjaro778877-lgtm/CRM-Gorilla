from sqlalchemy import Column, Integer, String, Float, Date, DateTime, Boolean, JSON, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from database import Base


class AdAccount(Base):
    __tablename__ = "ad_accounts"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)           # "Нутра Meta", "Гемблинг TT"
    platform = Column(String(30), nullable=False)        # meta | google | tiktok | telegram | trafficjunky | manual
    credentials = Column(JSON, default={})               # {"access_token": "...", "account_id": "..."}
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    stats = relationship("AdStats", back_populates="account", cascade="all, delete-orphan")


class AdStats(Base):
    __tablename__ = "ad_stats"

    id = Column(Integer, primary_key=True, index=True)
    account_id = Column(Integer, ForeignKey("ad_accounts.id", ondelete="CASCADE"), nullable=False)
    date = Column(Date, nullable=False)
    impressions = Column(Integer, default=0)
    clicks = Column(Integer, default=0)
    spend = Column(Float, default=0.0)
    ctr = Column(Float, default=0.0)
    conversions = Column(Integer, default=0)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    account = relationship("AdAccount", back_populates="stats")


class AdCreative(Base):
    __tablename__ = "ad_creatives"

    id = Column(Integer, primary_key=True, index=True)
    account_id = Column(Integer, ForeignKey("ad_accounts.id", ondelete="CASCADE"), nullable=False)
    ad_id = Column(String(100))
    ad_name = Column(String(200))
    date = Column(Date, nullable=False)
    image_url = Column(String(500), default="")
    spend = Column(Float, default=0.0)
    impressions = Column(Integer, default=0)
    clicks = Column(Integer, default=0)
    ctr = Column(Float, default=0.0)
    conversions = Column(Integer, default=0)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    account = relationship("AdAccount")
