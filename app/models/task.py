from sqlalchemy import Column, Integer, String, Text
from app.database import Base

class Task(Base):
    __tablename__ = "tasks"

    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    description = Column(Text)
    reward = Column(Integer, nullable=False)