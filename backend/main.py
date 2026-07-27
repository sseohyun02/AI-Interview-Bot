import os
import uuid
import tempfile

from fastapi import FastAPI, UploadFile, File, HTTPException, Depends, Form
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db, engine, Base
from models import User, Resume
import schemas
from auth import (
    hash_password,
    verify_password,
    create_access_token,
    get_current_user,
)

from core.interview_logic import extract_text_from_file
from core.interview_logic import preProcessing_Interview_from_text

# 서버 시작 시 테이블이 없으면 자동 생성 (이미 있으면 넘어감)
Base.metadata.create_all(bind=engine)

from core.interview_logic import (
    preProcessing_Interview,
    update_current_answer,
    evaluate_answer,
    decide_next_step,
    generate_question,
    change_strategy,
    summarize_interview,
)

app = FastAPI(title="AI Interview Bot API")

# 개발 단계에서는 전체 허용, 실제 프론트엔드 배포 주소가 정해지면 특정 도메인으로 좁힐 것
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# 세션 저장소 (인메모리)
# 주의: 서버 재시작 시 초기화됨, 인스턴스가 여러 개면 세션 공유 안 됨
# 포트폴리오/데모 단계에서는 문제없지만, 실서비스라면 Redis 등 외부 저장소로 교체 필요
sessions: dict[str, dict] = {}


class AnswerRequest(BaseModel):
    session_id: str
    answer: str


class InterviewResponse(BaseModel):
    session_id: str
    question: str | None = None
    ended: bool = False
    final_report: str | None = None
    
class StartRequest(BaseModel):
    resume_id: int


@app.post("/api/interview/start", response_model=InterviewResponse)
def start_interview(
    payload: StartRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),  # 로그인 필수
):
    # 내 이력서 중에서 해당 id를 찾음
    resume = db.query(Resume).filter(
        Resume.id == payload.resume_id,
        Resume.owner_id == current_user.id,
    ).first()
    if not resume:
        raise HTTPException(status_code=404, detail="이력서를 찾을 수 없습니다.")

    # 저장된 이력서 텍스트로 면접 준비
    state = preProcessing_Interview_from_text(resume.content)

    session_id = str(uuid.uuid4())
    sessions[session_id] = {"state": state, "ended": False}

    return InterviewResponse(
        session_id=session_id,
        question=state["current_question"],
    )


@app.post("/api/interview/answer", response_model=InterviewResponse)
async def submit_answer(payload: AnswerRequest):
    """답변을 제출받아 평가 후 다음 질문 또는 최종 리포트를 반환한다."""
    session = sessions.get(payload.session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="세션을 찾을 수 없습니다.")
    if session["ended"]:
        raise HTTPException(status_code=400, detail="이미 종료된 인터뷰입니다.")

    state = update_current_answer(session["state"], payload.answer)
    state = evaluate_answer(state)
    state = decide_next_step(state)

    next_step = state.get("next_step", "")
    if next_step == "generate":
        state = generate_question(state)
    elif next_step == "change_strategy":
        state = change_strategy(state)
    elif next_step == "summarize":
        state = summarize_interview(state)

    session["state"] = state

    if state.get("next_step") == "end":
        session["ended"] = True
        final_report = state.get("final_report", "인터뷰가 종료되었습니다.")
        return InterviewResponse(
            session_id=payload.session_id,
            ended=True,
            final_report=final_report,
        )

    return InterviewResponse(
        session_id=payload.session_id,
        question=state.get("current_question", "다음 질문을 준비 중입니다..."),
    )

# === 회원가입 ===
@app.post("/api/auth/register", response_model=schemas.UserOut)
def register(user: schemas.UserCreate, db: Session = Depends(get_db)):
    # 이미 가입된 이메일인지 확인
    existing = db.query(User).filter(User.email == user.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="이미 가입된 이메일입니다.")

    # 새 회원 생성 (비밀번호는 해싱해서 저장)
    new_user = User(
        email=user.email,
        hashed_password=hash_password(user.password),
        name=user.name,
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)  # DB가 채워준 id 등을 다시 읽어옴
    return new_user


# === 로그인 ===
@app.post("/api/auth/login", response_model=schemas.Token)
def login(credentials: schemas.UserLogin, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == credentials.email).first()
    # 이메일이 없거나 비밀번호가 틀리면 동일한 에러 (보안상 어느 쪽이 틀렸는지 안 알려줌)
    if not user or not verify_password(credentials.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="이메일 또는 비밀번호가 올바르지 않습니다.")

    # 토큰 발급
    token = create_access_token(user.id)
    return {"access_token": token, "token_type": "bearer"}


# === 내 정보 조회 (로그인 확인용) ===
@app.get("/api/auth/me", response_model=schemas.UserOut)
def read_me(current_user: User = Depends(get_current_user)):
    return current_user

# === 이력서 업로드 (저장) ===
@app.post("/api/resumes", response_model=schemas.ResumeOut)
async def upload_resume(
    title: str = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),  # 로그인 필수
):
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in (".pdf", ".docx"):
        raise HTTPException(status_code=400, detail="PDF 또는 DOCX 파일만 업로드 가능합니다.")

    # 파일을 임시 저장 후 텍스트 추출
    with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
        tmp.write(await file.read())
        tmp_path = tmp.name
    try:
        content = extract_text_from_file(tmp_path)
    finally:
        os.remove(tmp_path)

    # DB에 저장 (현재 로그인한 사용자의 이력서로)
    resume = Resume(title=title, content=content, owner_id=current_user.id)
    db.add(resume)
    db.commit()
    db.refresh(resume)
    return schemas.ResumeOut(
        id=resume.id,
        title=resume.title,
        created_at=str(resume.created_at),
    )


# === 내 이력서 목록 조회 ===
@app.get("/api/resumes", response_model=list[schemas.ResumeOut])
def list_resumes(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    resumes = db.query(Resume).filter(Resume.owner_id == current_user.id).all()
    return [
        schemas.ResumeOut(id=r.id, title=r.title, created_at=str(r.created_at))
        for r in resumes
    ]


# === 이력서 삭제 ===
@app.delete("/api/resumes/{resume_id}")
def delete_resume(
    resume_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    resume = db.query(Resume).filter(
        Resume.id == resume_id,
        Resume.owner_id == current_user.id,  # 남의 이력서는 못 지우게
    ).first()
    if not resume:
        raise HTTPException(status_code=404, detail="이력서를 찾을 수 없습니다.")
    db.delete(resume)
    db.commit()
    return {"deleted": True}


@app.get("/api/interview/report/{session_id}", response_model=InterviewResponse)
async def get_report(session_id: str):
    """세션의 현재 상태(진행 중이면 현재 질문, 종료됐으면 최종 리포트)를 반환한다."""
    session = sessions.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="세션을 찾을 수 없습니다.")

    state = session["state"]
    if session["ended"]:
        return InterviewResponse(
            session_id=session_id,
            ended=True,
            final_report=state.get("final_report", ""),
        )
    return InterviewResponse(
        session_id=session_id,
        question=state.get("current_question"),
    )


@app.get("/healthz")
async def health_check():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
