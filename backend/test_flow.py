"""백엔드 전체 흐름 end-to-end 테스트 스크립트"""
import io
import requests
from docx import Document

BASE = "http://localhost:8080"

# 테스트 계정 정보 (매번 재실행 가능하도록 random suffix 사용 가능)
EMAIL = "test@example.com"
PASSWORD = "testpass123"
NAME = "테스트유저"


def pretty(label, resp):
    """응답을 간결하게 출력"""
    body = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else resp.text
    print(f"[{label}] {resp.status_code} | {str(body)[:140]}")


# 1) 헬스체크
pretty("healthz", requests.get(f"{BASE}/healthz"))

# 2) 회원가입 (이미 있으면 400, 무시하고 진행)
r = requests.post(f"{BASE}/api/auth/register",
                  json={"email": EMAIL, "password": PASSWORD, "name": NAME})
pretty("register", r)

# 3) 로그인 -> 토큰
r = requests.post(f"{BASE}/api/auth/login",
                  json={"email": EMAIL, "password": PASSWORD})
pretty("login", r)
token = r.json()["access_token"]
headers = {"Authorization": f"Bearer {token}"}

# 4) 테스트용 이력서 docx 를 메모리에서 생성
doc = Document()
doc.add_paragraph("이름: 테스트 유저")
doc.add_paragraph("학력: 서울XX대학교 산업공학과 졸업 (2026)")
doc.add_paragraph("경험: Python/FastAPI 로 OCR 백엔드 개발, 인식률 86% -> 94% 개선")
doc.add_paragraph("기술: Python, FastAPI, PostgreSQL, Docker, LangChain")
doc.add_paragraph("프로젝트: AI 면접 봇, 임대차 계약서 검토 시스템")
buf = io.BytesIO()
doc.save(buf)
buf.seek(0)

# 5) 이력서 업로드 (company, position 포함)
files = {"file": ("test_resume.docx", buf,
                  "application/vnd.openxmlformats-officedocument.wordprocessingml.document")}
form = {"title": "테스트 이력서", "company": "네이버", "position": "AI 엔지니어"}
r = requests.post(f"{BASE}/api/resumes", files=files, data=form, headers=headers)
pretty("upload", r)
resume_id = r.json()["id"]

# 6) 면접 시작
r = requests.post(f"{BASE}/api/interview/start",
                  json={"resume_id": resume_id}, headers=headers)
pretty("start", r)
data = r.json()
session_id = data["session_id"]
print(f"  첫 질문: {data['question']}")
print()

# 7) 답변을 여러 번 제출해 흐름 확인
answers = [
    "저는 OCR 백엔드를 Python 과 FastAPI 로 개발하면서 전처리 파이프라인을 담당했고, "
    "네이버의 AI 서비스가 일상적으로 많은 사용자에게 가치를 주는 점이 매력적이었습니다. "
    "협업 시 Jira 와 Slack 으로 매일 스탠드업을 하고, 블로커가 생기면 바로 공유해 팀원 도움을 구했습니다. "
]

for i, ans in enumerate(answers, 1):
    r = requests.post(f"{BASE}/api/interview/answer",
                      json={"session_id": session_id, "answer": ans},
                      headers=headers)
    data = r.json()
    pretty(f"turn {i}", r)
    if data.get("ended"):
        print()
        print("=" * 60)
        print(" 면접 종료 - 최종 리포트")
        print("=" * 60)
        print(data["final_report"])
        break
    print(f"  다음 질문: {data.get('question')}")
    print()

# 8) 이력서 삭제 (정리)
r = requests.delete(f"{BASE}/api/resumes/{resume_id}", headers=headers)
pretty("delete resume", r)