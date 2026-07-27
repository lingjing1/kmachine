from sqlalchemy import Column, Integer, Text, JSON, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy import create_engine
from sqlalchemy import and_, or_
from datetime import datetime
import sys
import os

from backend.app.config.settings import settings

Base = declarative_base()

oj_db_uri = settings.oj_database_url
engine = create_engine(oj_db_uri)
Session = sessionmaker(bind=engine)

# define Problem model
class Problem(Base):
    __tablename__ = 'problem'
    id = Column(Integer, primary_key=True)
    title = Column(Text)
    description = Column(Text)
    input_description = Column(Text)
    output_description = Column(Text)
    samples = Column(JSON)
    _id = Column(Text)
    create_time = Column(DateTime)

    def to_dict(self):
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "input_description": self.input_description,
            "output_description": self.output_description,
            "samples": self.samples,
            "_id": self._id,
            "create_time": self.create_time.isoformat() if self.create_time else None,
        }
    

def get_problems_by_chapter(chapter_id, start_time=None, end_time=None):
    session = Session()
    try:
        # 默認範圍設定
        if not start_time:
            start_time = "2025-08-14T00:00:00"  # 默認開始時間
        if isinstance(start_time, str):
            start_time = datetime.fromisoformat(start_time)
        if end_time and isinstance(end_time, str):
            end_time = datetime.fromisoformat(end_time)
        
        if chapter_id == 'C1':
            print('##########', Problem._id)
            
        # 查詢符合條件的題目
        query = session.query(Problem._id, Problem.title, Problem.create_time).filter(
            and_(
                Problem._id.like(f"{chapter_id}_%"),
                Problem.create_time >= start_time,
            )
        )
        
        if end_time:
            query = query.filter(Problem.create_time <= end_time)
            
        problems = query.order_by(Problem._id.asc()).all()
        
        # 返回結果
        return [{"_id": p._id, "title": p.title, "create_time": p.create_time.isoformat() if p.create_time else None} for p in problems]
    finally:
        session.close()

# 透過 Problem._id 查詢題目內容
def get_problem_by_id(problem_id):
    session = Session()
    print("[oj_models.py]進入get_problem_by_id!, problem_id=", problem_id, "type=", type(problem_id))
    try:
        # 查詢符合題號的題目
        problem = session.query(Problem).filter(Problem._id == problem_id).first()
        if not problem:
            return None  # 題目不存在

        # 將結果轉換為字典
        data = problem.to_dict()

        # 解析 samples 欄位
        data["samples"] = [{"input": s.get("input"), "output": s.get("output")} for s in data.get("samples", [])]

        return data
    finally:
        session.close()

# 透過 Problem.id 查詢題目內容
def get_problem_by_problem_id(problem_id):
    session = Session()
    try:
        # 透過 Problem.id 查詢，而不是 Problem._id
        problem = session.query(Problem).filter(Problem.id == problem_id).first()
        if not problem:
            return None  # 題目不存在

        # 將結果轉換為字典
        data = problem.to_dict()
        
        # 解析 samples 欄位
        data["samples"] = [{"input": s.get("input"), "output": s.get("output")} for s in data.get("samples", [])]

        return data
    finally:
        session.close()