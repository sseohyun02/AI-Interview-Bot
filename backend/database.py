import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from dotenv import load_dotenv

# .env 파일에서 환경변수 로드
load_dotenv()

DATABASE_URL = os.environ["DATABASE_URL"]

# DB 엔진: 실제 PostgreSQL과 연결하는 통로
engine = create_engine(DATABASE_URL)

# 세션: DB와 대화하는 하나의 작업 단위 (요청마다 하나씩 만들어 씀)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base: 모든 테이블 모델(클래스)이 상속받는 부모
Base = declarative_base()


# 각 API 요청마다 DB 세션을 열고, 끝나면 닫아주는 함수
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()