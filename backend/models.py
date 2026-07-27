from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from database import Base


# users 테이블: 회원 정보
class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)  # 로그인 아이디
    hashed_password = Column(String, nullable=False)                 # 암호화된 비밀번호
    name = Column(String, nullable=False)                            # 이름
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # 이 회원이 올린 이력서들 (1:N 관계)
    resumes = relationship("Resume", back_populates="owner")


# resumes 테이블: 이력서
class Resume(Base):
    __tablename__ = "resumes"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False)          # 이력서 제목 (예: "네이버 지원용")
    content = Column(Text, nullable=False)          # 이력서에서 추출한 텍스트
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # 이 이력서의 주인 (users 테이블과 연결)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    owner = relationship("User", back_populates="resumes")