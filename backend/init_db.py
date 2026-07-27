from database import Base, engine
import models  # models.py를 불러와야 테이블 정의가 등록됨

# models.py에 정의된 모든 테이블을 실제 DB에 생성
Base.metadata.create_all(bind=engine)
print("테이블 생성 완료")