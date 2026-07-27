import os
import uuid
import tempfile

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

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


@app.post("/api/interview/start", response_model=InterviewResponse)
async def start_interview(file: UploadFile = File(...)):
    """이력서 파일을 업로드받아 인터뷰 세션을 시작한다."""
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in (".pdf", ".docx"):
        raise HTTPException(status_code=400, detail="PDF 또는 DOCX 파일만 업로드 가능합니다.")

    # 업로드된 파일을 임시 경로에 저장 (기존 로직이 파일 경로를 입력으로 받는 구조라서)
    with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
        tmp.write(await file.read())
        tmp_path = tmp.name

    try:
        state = preProcessing_Interview(tmp_path)
    finally:
        os.remove(tmp_path)

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
