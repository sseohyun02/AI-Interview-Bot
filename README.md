# AI Interview Bot: 이력서 기반 AI 모의면접 서비스
이력서와 지원 기업·직무를 바탕으로 면접 질문을 생성하고, 답변 평가에 따라 심화 질문과 다음 질문을 선택하며 최종 피드백을 제공하는 서비스입니다.

## 프로젝트 개요

이력서에 담긴 경험과 역량을 바탕으로 질문을 구성하고, 답변에서 보완할 부분을 추가 질문으로 확인할 수 있도록 개발했습니다.
LangGraph로 답변 평가와 면접 진행 분기를 연결하고, 면접 세션별로 분야별 평가 점수·심화 질문 횟수·대화 로그를 유지해 여러 답변에 걸친 평가와 최종 보고서 생성을 지원합니다.

## 주요 기능

1. **회원가입 및 로그인**: 비밀번호 해싱과 JWT 인증을 통해 회원별 이력서를 관리합니다.
2. **이력서 업로드 및 관리**: PDF·DOCX에서 텍스트를 추출하고, 지원 기업·직무와 함께 저장합니다. 등록한 이력서는 조회·삭제할 수 있습니다.
3. **이력서 기반 질문 생성**: 이력서 요약과 핵심 키워드를 바탕으로 경험·동기·논리 분야의 질문을 구성합니다.
4. **답변 평가 및 면접 진행 분기**: 구체성·일관성·적합성·논리성을 0/1로 평가하고, 분야별 누적 평균과 심화 질문 횟수에 따라 추가 질문·분야 전환·종료를 결정합니다.
5. **참고자료 기반 심화 질문**: 현재 질문·답변과 부족한 평가 항목을 바탕으로 Chroma에 저장된 면접 질문 예시를 검색하고, 이를 참고해 심화 질문을 생성합니다.
6. **최종 피드백 보고서**: 분야별 항목 평균, 종합 점수, 강점과 개선 항목, 종합 의견을 텍스트 보고서로 제공합니다.

## 서비스 화면

| 로그인 | 면접 준비 |
|:---:|:---:|
| <img width="480" alt="로그인 화면" src="https://github.com/user-attachments/assets/a41d3f4b-7e0c-41d1-9c08-c947d8561363" /> | <img width="480" alt="면접 준비 화면" src="https://github.com/user-attachments/assets/625c4d2f-71a2-49a4-94bb-edca1d76b1ee" /> |

| AI 면접 진행 | 면접 분석 리포트 |
|:---:|:---:|
| <img width="480" alt="AI 면접 진행 화면" src="https://github.com/user-attachments/assets/6ba809b2-2b23-4e26-bc5d-0a2e09f63a50" /> | <img width="480" alt="면접 분석 리포트" src="https://github.com/user-attachments/assets/fde20fb3-287e-4ec7-af93-0ef45305b4a7" /> |

## 시스템 아키텍처

### 전체 파이프라인

```mermaid
flowchart TD
    A["이력서 업로드 · 지원 기업 및 직무 입력"] --> B["텍스트 추출 · 이력서 요약 및 키워드 분석"]
    B --> C["분야별 질문 구성 · 첫 질문 제시"]
    C --> D["사용자 답변 입력"]
    D --> E["답변 평가 · 분야별 점수 누적"]
    E --> F{"면접 진행 판단"}

    F -->|추가 확인 필요| G["참고자료 검색 · 심화 질문 생성"]
    F -->|다음 분야로 이동| H["다음 분야 질문 선택"]
    F -->|면접 종료| I["최종 피드백 보고서 생성"]

    G --> D
    H --> D
```

분야별 누적 평균이 기준에 도달하거나 심화 질문을 2회 진행하면 다음 분야로 이동합니다. 마지막 분야에서는 같은 조건에 따라 면접을 종료합니다.

### 인프라 구조

```mermaid
flowchart TD
    A["사용자 브라우저<br/>React · Vite"] -->|API 요청| B["FastAPI 백엔드"]
    B --> C["LangGraph<br/>답변 평가 · 진행 분기"]

    B -->|회원 · 이력서 저장 및 조회| D[("PostgreSQL")]
    B <-->|면접 상태 저장 및 갱신| E["서버 메모리<br/>점수 · 심화 횟수 · 대화 로그"]
    C -->|심화 질문 참고자료 검색| F[("Chroma")]
    C -->|평가 · 질문 · 피드백 생성| G["Gemini API"]
    B -->|이력서 분석 · 초기 질문 구성| G
```

면접 상태는 서버 메모리에 저장되어 서버 재시작 시 초기화됩니다. 참고 질문은 별도 스크립트에서 한국어 임베딩 모델로 벡터화해 로컬 Chroma에 저장하며, 면접 중에는 심화 질문 생성 시 검색합니다.

## 기술 스택

| 분야 | 기술 스택 |
|:---:|---|
| **Frontend** | ![React](https://img.shields.io/badge/React-61DAFB?style=flat-square&logo=react&logoColor=white) ![JavaScript](https://img.shields.io/badge/JavaScript-F7DF1E?style=flat-square&logo=javascript&logoColor=black) ![Vite](https://img.shields.io/badge/Vite-646CFF?style=flat-square&logo=vite&logoColor=white) |
| **Backend** | ![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=flat-square&logo=fastapi&logoColor=white) ![Python](https://img.shields.io/badge/Python-3776AB?style=flat-square&logo=python&logoColor=white) ![SQLAlchemy](https://img.shields.io/badge/SQLAlchemy-D71F00?style=flat-square&logo=sqlalchemy&logoColor=white) |
| **AI / RAG** | LangChain · LangGraph · Gemini API (`gemini-3.5-flash-lite`) · Sentence Transformers (`jhgan/ko-sroberta-multitask`) |
| **문서 처리** | PyMuPDF · python-docx |
| **DB** | ![PostgreSQL](https://img.shields.io/badge/PostgreSQL-4169E1?style=flat-square&logo=postgresql&logoColor=white) ![Chroma](https://img.shields.io/badge/Chroma-555555?style=flat-square) |
| **인증** | ![JWT](https://img.shields.io/badge/JWT-000000?style=flat-square&logo=jsonwebtokens&logoColor=white) ![bcrypt](https://img.shields.io/badge/bcrypt-555555?style=flat-square) |

## 폴더 구조

```text
AI-Interview-Bot/
├── backend/                         # FastAPI 백엔드
│   ├── main.py                      # 회원·이력서·면접 API 및 세션 관리
│   ├── auth.py                      # 비밀번호 해싱 및 JWT 인증
│   ├── database.py                  # PostgreSQL 연결 및 세션 설정
│   ├── models.py                    # 회원·이력서 DB 모델
│   ├── schemas.py                   # 회원·이력서 API 스키마
│   ├── init_db.py                   # PostgreSQL 테이블 생성 스크립트
│   ├── build_interview_db.py        # 참고 질문 추출·임베딩·Chroma 적재
│   ├── requirements.txt            # Python 의존성
│   ├── test_flow.py                # API 흐름 확인 스크립트
│   ├── core/
│   │   └── interview_logic.py      # 이력서 분석·검색·평가·LangGraph 흐름
│   ├── assets/
│   │   └── interview_questions.pdf # 별도 준비하는 참고자료 (Git 제외)
│   └── data/                       # 로컬 생성 데이터 (Git 제외)
│       ├── interview_questions_preview.json # 추출 질문 검토용
│       └── chroma_interview_ko/     # Chroma DB 저장 폴더
│
└── frontend/                        # React + Vite 프론트엔드
    ├── package.json                 # 프론트엔드 의존성 및 실행 명령
    ├── vite.config.js               # Vite 설정
    └── src/
        ├── App.jsx                  # 화면 전환 및 로그인 상태 관리
        ├── api.js                   # 백엔드 API 호출 및 토큰 관리
        ├── main.jsx                 # React 진입점
        ├── index.css                # 공통 스타일
        └── screens/
            ├── Auth.jsx             # 회원가입·로그인
            ├── Home.jsx             # 등록 이력서 목록
            ├── Prep.jsx             # 이력서 업로드 및 면접 준비
            ├── Interview.jsx        # 면접 질문·답변
            ├── Analyzing.jsx        # 분석 진행 표시
            └── Report.jsx           # 최종 피드백 표시
```

<details>
<summary>설치 및 실행 방법</summary>

### 사전 요구사항

- Python 환경: 아래 안내는 Python 3.11 이상을 기준으로 합니다.
- Node.js 22.13 이상인 22.x 또는 Node.js 24 이상
- PostgreSQL 데이터베이스 및 접속 정보
- Gemini API Key

### 백엔드 실행

저장소를 내려받은 뒤 `backend` 폴더에서 실행합니다.

```bash
git clone https://github.com/sseohyun02/AI-Interview-Bot.git
cd AI-Interview-Bot/backend

# 의존성 설치
python -m pip install -r requirements.txt
```

`backend/.env` 파일을 만들고 아래 ‘환경 변수 설정’ 항목의 값을 입력합니다.
PostgreSQL 서버를 실행하고, 접속할 데이터베이스를 미리 생성해야 합니다.

#### 면접 참고자료 DB 구축

참고자료 PDF와 생성된 데이터는 저장소에 포함하지 않습니다.
사용할 면접 질문 PDF를 `backend/assets/interview_questions.pdf`에 준비합니다.

`backend` 폴더에서 질문을 추출합니다.

```bash
python build_interview_db.py
```

생성된 `data/interview_questions_preview.json`에서 질문 누락이나 불필요한 문구를 확인·수정한 뒤, 임베딩과 적재를 실행합니다.

```bash
python build_interview_db.py --build
```

한국어 임베딩 모델은 최초 실행 시 다운로드되며 로컬 CPU에서 실행됩니다.
DB는 `backend/data/chroma_interview_ko/`에 저장됩니다.

같은 내용으로 재실행하면 이미 저장된 텍스트는 건너뜁니다.
원본에서 삭제하거나 수정한 질문의 기존 DB 항목은 자동 삭제되지 않습니다.

#### API 서버 실행

```bash
python -m uvicorn main:app --reload --host 0.0.0.0 --port 8080
# API 문서: http://localhost:8080/docs
```

서버 시작 시 회원·이력서 테이블이 없으면 생성합니다.
심화 질문 생성 시 미리 구축한 Chroma DB와 로컬 임베딩 모델을 불러와 검색합니다.

### 프론트엔드 실행

`frontend/.env.local` 파일에 백엔드 주소를 설정합니다.

```env
VITE_API_BASE=http://localhost:8080
```

새 터미널에서 실행합니다.

```bash
cd AI-Interview-Bot/frontend

# 의존성 설치
npm ci

# 개발 서버 실행
npm run dev
# 기본 접속 주소: http://localhost:5173
```

### 환경 변수 설정

`backend/.env`:

```env
# Gemini API
GOOGLE_API_KEY=your-gemini-api-key

# PostgreSQL
DATABASE_URL=postgresql+psycopg://your-db-user:your-db-password@localhost:5432/your-db-name

# JWT 서명 키
SECRET_KEY=your-random-secret-key
```

</details>
