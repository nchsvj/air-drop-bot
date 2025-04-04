# models.py
from sqlalchemy import Column, BigInteger, Integer, String
from app.database.db import Base

class User(Base):
    __tablename__ = "users"

    id = Column(BigInteger, primary_key=True)
    balance = Column(Integer, default=0)

class Task(Base):
    __tablename__ = "tasks"

    id = Column(Integer, primary_key=True)
    level = Column(String, nullable=False)   # 'easy', 'normal', 'hard'
    question = Column(String, nullable=False)
    answer = Column(String, nullable=False)
    reward = Column(Integer, nullable=False)
