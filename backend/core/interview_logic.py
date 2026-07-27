import pandas as pd
import numpy as np
import os
import ast
import fitz  # PyMuPDF
from docx import Document
import random
import warnings
import random
warnings.filterwarnings("ignore", category=DeprecationWarning)

from dotenv import load_dotenv
load_dotenv()

from typing import Annotated, Literal, Sequence, TypedDict

from langchain_core.messages import BaseMessage, HumanMessage
from langchain_core.output_parsers import StrOutputParser, CommaSeparatedListOutputParser
from langchain_core.prompts import PromptTemplate, ChatPromptTemplate
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_community.vectorstores import Chroma

from langgraph.graph import StateGraph, START, END
from typing import TypedDict, List, Dict
from pydantic import BaseModel, Field
from typing import List
from tabulate import tabulate
import tempfile

from langchain_community.document_loaders import UnstructuredWordDocumentLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter

def extract_text_from_file(file_path: str) -> str:
  ext = os.path.splitext(file_path)[1].lower()
  if ext == ".pdf":
    doc = fitz.open(file_path)
    text = "\n".join(page.get_text() for page in doc)
    doc.close()
    return text
  elif ext == ".docx":
    doc = Document(file_path)
    return "\n".join(p.text for p in doc.paragraphs if p.text.strip())
  else:
    raise ValueError("지원하지 않는 파일 형식입니다. PDF 또는 DOCX만 허용됩니다.")


class InterviewState(TypedDict):
    # 고정 정보
    resume_text: str
    resume_summary: str
    resume_keywords: List[str]
    question_strategy: Dict[str, Dict]

    # 인터뷰 로그
    current_question: str
    current_answer: str
    current_strategy: str
    conversation: List[Dict[str, str]]
    evaluation : List[Dict[str, str]]
    next_step : str
    deep_counts : Dict[str, Dict]



# LLM 출력 형식 (pydantic 모델)
class ResumeAnalysis(BaseModel):
    summary: str = Field(..., description="이력서 주요 내용을 3~5문장으로 요약한 문장")
    keywords: List[str] = Field(..., description="이력서의 핵심 역량 및 키워드 목록")

# llm 모델 정의
llm = ChatGoogleGenerativeAI(model="gemini-flash-latest")

def analyze_resume(state: InterviewState) -> InterviewState:
  '''
  이력서를 분석해 핵심을 요약하고 주요 키워드를 추출
  '''
  # 1. 이력서 텍스트 가져오기
  resume_text = state["resume_text"]

  # 2. 프롬프트 구성
  prompt_template = ChatPromptTemplate.from_messages([
      ("system",
        "당신은 인사 당담자입니다. 다음 이력서 텍스트를 분석하여 핵심 요약과 주요 키워드를 도출하세요. "
        "결과는 JSON 형태로 반환하세요. "
        "1. summary: 이력서 핵심 요약 (3~5문장) "
        "2. keywords: 주요 키워드 목록 (핵심 역량, 기술, 성과, 강점 등)"),
      ("human", "분석할 이력서 텍스트:\n---\n{resume_text}")
  ])

  # 3. LLM 실행 (Pydantic 구조화 출력)
  chain = prompt_template | llm.with_structured_output(ResumeAnalysis)
  result: ResumeAnalysis = chain.invoke({"resume_text": resume_text})

  # 4. 상태 업데이트 및 반환
  return {
      **state,
      "resume_summary": result.summary,
      "resume_keywords": result.keywords,
  }

class QSItem(BaseModel):
    direction: str = Field(..., description="질문 방향")
    examples: List[str] = Field(..., description="예시 질문 목록(2~3개)")

class QSOutput(BaseModel):
    experience: QSItem
    motivation: QSItem
    logic: QSItem

class QSMultiOutput(BaseModel):  # 세 명의 면접관
    potential: QSOutput       # A 면접관 (잠재력)
    organization: QSOutput    # B 면접관 (조직)
    job: QSOutput             # C 면접관 (직무)

def generate_question_strategy(state: InterviewState) -> InterviewState:
    summary = state.get("resume_summary", "")
    keywords = state.get("resume_keywords", [])

    prompt = ChatPromptTemplate.from_messages([
        ("system",
         "당신은 시니어 인사담당 면접관입니다.\n"
         "아래 이력서를 기반으로 **3명의 면접관(A/B/C)**에 대해 면접 질문 전략을 만듭니다.\n\n"

         "면접관 역할:\n"
         "A = 잠재력 평가 (도전, 문제 해결, 성장 가능성)\n"
         "B = 조직 적합도 평가 (협업, 소통, 조직문화)\n"
         "C = 직무 역량 평가 (기술/업무 수행능력, 성과)\n\n"

         "각 면접관은 아래 3개 항목에 대해 질문 생성:\n"
         "1) 경력 및 경험\n"
         "2) 동기 및 커뮤니케이션\n"
         "3) 논리적 사고\n\n"

         "각 항목에 대해 반드시 다음 정보를 포함:\n"
         "- direction: 평가 의도/목적 (1~2문장)\n"
         "- examples: 실제 면접 질문 2~3개 (구체적, 맥락 기반, 정중체)\n\n"

         "출력 형식은 JSON ONLY이며 다음 스키마를 따르세요.\n"
         "{{\n"
         "  \"potential\": {{ \"experience\": ..., \"motivation\": ..., \"logic\": ... }},\n"
         "  \"organization\": {{ \"experience\": ..., \"motivation\": ..., \"logic\": ... }},\n"
         "  \"job\": {{ \"experience\": ..., \"motivation\": ..., \"logic\": ... }}\n"
         "}}\n\n"

         "예시 질문 스타일 가이드:\n"
         "- '~했던 경험이 있나요?' '~어떤 기여를 했나요?' '~어떻게 해결했나요?' 형식\n"
         "- 숫자/성과/구체적 사례 포함\n"
         "- 협업, 난관 해결, 역할 분명히 질문\n"
         "- 모호한 질문 금지\n"
         "- JSON 외 텍스트 출력 금지"
        ),
        ("human",
         "이력서 요약:\n{summary}\n\n"
         "주요 키워드:\n{keywords}\n\n"
         "**반드시 JSON만 출력하세요.**")
    ])

    chain = prompt | llm.with_structured_output(QSMultiOutput)
    result: QSMultiOutput = chain.invoke({
        "summary": summary,
        "keywords": ", ".join(keywords) if isinstance(keywords, list) else str(keywords)
    })

    strategy_dict = {
        "경험": {
            "A": result.potential.experience.examples[0],  # 첫 질문만 사용
            "B": result.organization.experience.examples[0],
            "C": result.job.experience.examples[0],
        },
        "동기": {
            "A": result.potential.motivation.examples[0],
            "B": result.organization.motivation.examples[0],
            "C": result.job.motivation.examples[0],
        },
        "논리": {
            "A": result.potential.logic.examples[0],
            "B": result.organization.logic.examples[0],
            "C": result.job.logic.examples[0],
        },
    }

    state["question_strategy"] = strategy_dict
    return state


def preProcessing_Interview(file_path: str) -> InterviewState:
    """이력서 파일 경로 입력 → 텍스트 추출 후 처리"""
    resume_text = extract_text_from_file(file_path)
    return preProcessing_Interview_from_text(resume_text)


def preProcessing_Interview_from_text(resume_text: str) -> InterviewState:
    """이력서 텍스트 입력 → 분석 → 질문전략 생성 → 첫 질문 선택"""

    # 초기 state 설정
    state: InterviewState = {
        "resume_text": resume_text,
        "resume_summary": "",
        "resume_keywords": [],
        "question_strategy": {},
        "current_question": "",
        "current_answer": "",
        "current_strategy": "",
        "conversation": [],
        "evaluation": [],
        "next_step": "",
        "deep_counts": {}
    }

    # 1) Resume 분석
    state = analyze_resume(state)

    # 2) 질문 전략 생성
    state = generate_question_strategy(state)

    # 3) 첫 질문 선택
    strategy = state["question_strategy"]
    categories = ["경험", "동기", "논리"]
    interviewers = ["A", "B", "C"]
    cat = categories[0]
    iv = random.choice(interviewers)
    selected_question = strategy[cat][iv]

    state["current_question"] = selected_question
    state["current_strategy"] = f"{cat}"

    return state


def update_current_answer(state: InterviewState, user_answer: str) -> InterviewState:
    return {
        **state,
        "current_answer": user_answer.strip()
    }

# ===== (변경 없음) 구조화 출력 스키마 =====
Binary = Literal[0, 1]

class BinCriterion(BaseModel):
    score: Binary = Field(..., description="0=부족, 1=우수")
    rationale: str = Field(..., description="간단 근거 1~2문장")

class FourCriteriaEval(BaseModel):
    specificity: BinCriterion  # 구체성
    consistency: BinCriterion  # 일관성
    fit: BinCriterion          # 적합성
    logic: BinCriterion        # 논리성


# ===== 헬퍼: state 스키마 보정 =====
def _ensure_state_schema(state: Dict) -> Dict:
    ev = state.get("evaluation")
    if ev is None:
        ev = {}
    elif isinstance(ev, list):
        new_ev = {}
        for item in ev:
            if not isinstance(item, dict):
                continue
            strat = item.get("strategy") or item.get("분야") or "기본"
            if all(k in item for k in ("구체성", "일관성", "적합성", "논리성")):
                new_ev[strat] = {
                    "구체성": item["구체성"],
                    "일관성": item["일관성"],
                    "적합성": item["적합성"],
                    "논리성": item["논리성"],
                }
            elif "scores" in item and isinstance(item["scores"], dict):
                sc = item["scores"]
                new_ev[strat] = {
                    "구체성": sc.get("specificity") or sc.get("concreteness") or 0,
                    "일관성": sc.get("consistency") or sc.get("coherence") or 0,
                    "적합성": sc.get("fit") or sc.get("relevance") or 0,
                    "논리성": sc.get("logic") or sc.get("soundness") or 0,
                }
        ev = new_ev
    elif not isinstance(ev, dict):
        ev = {}
    conv = state.get("conversation")
    if not isinstance(conv, list):
        conv = []
    state["evaluation"] = ev
    state["conversation"] = conv
    return state


# ===== 헬퍼: 0점 지표 기반 후속질문 생성 =====
def _make_followup_question(strategy: str, zeros: List[str], prev_q: str) -> str:
    # 한글 지표명 표준화
    norm = {"구체적":"구체성", "구체성":"구체성", "일관성":"일관성", "적합성":"적합성", "논리성":"논리성"}
    zeros = [norm.get(z, z) for z in zeros]

    parts = []
    if "구체성" in zeros:
        parts.append("정확도/처리시간 등 **수치**, 본인 **역할**, 적용한 **방법**(전처리/모델/튜닝), 그리고 **Before→After 변화**를 수치로 알려주세요.")
    if "일관성" in zeros:
        parts.append("주장→근거→사례의 **흐름**이 보이도록 STAR 구조(상황-과제-행동-결과)로 정리해서 답해주세요.")
    if "적합성" in zeros:
        parts.append("해당 경험이 **KT의 AI/DX 전략** 혹은 **지원 직무 과업**과 **어떻게 연결**되는지 명확히 밝혀주세요.")
    if "논리성" in zeros:
        parts.append("문제 **원인** 분석→시도한 **대안**→선택 **근거**→**결과** 및 **교훈** 순서로 설명해주세요.")

    tail = " ".join(parts) if parts else "핵심 근거와 수치를 보강해 구체적으로 답해주세요."
    head = "이전 답변을 보강해주세요. " if prev_q else ""
    return f"{head}{strategy} 영역에서 다음을 중심으로 다시 답변해 주세요. {tail}"


# ===== 메인: 평가 + 라우팅(조건1/2) + few-shot 프롬프트 =====
# ===== 메인: 평가 + 라우팅(조건1/2) + few-shot 프롬프트 =====
def evaluate_answer(state: Dict) -> Dict:
    state = _ensure_state_schema(state)

    question = state.get("current_question", "")
    answer   = state.get("current_answer", "")
    strategy = state.get("current_strategy", "기본")
    resume_ctx = {
        "summary": state.get("resume_summary", ""),
        "keywords": ", ".join(state.get("resume_keywords", []))
    }

    # -------------------------------------------------
    # 1. 일관성 기본값 1점 부여 (이후 LLM 결과에 따라 교체)
    # -------------------------------------------------
    evaluation: Dict[str, Dict] = state.get("evaluation", {})
    if strategy not in evaluation:
        evaluation[strategy] = {
            "구체성": 0,
            "일관성": 1,   # ← 기본 1점
            "적합성": 0,
            "논리성": 0,
            "question": question,
            "answer": answer,

            "_n": 0,
            "_sum_구체성": 0,
            "_sum_일관성": 0,
            "_sum_적합성": 0,
            "_sum_논리성": 0,
        }

    # -------------------------------------------------
    # 2. LLM 평가 (구조화 출력)
    # -------------------------------------------------
    prompt = ChatPromptTemplate.from_messages([
        ("system",
         "너는 KT 면접관이다. 다음 4개 항목을 **서로 독립적으로** 0 또는 1로 채점하라. "
         "하나의 항목이 1이라고 해서 다른 항목도 반드시 1일 필요는 없다. "
         "각 항목은 score(0/1)와 rationale(1~2문장)만 포함한다.\n"
         "- 구체성: 수치·사실·사례·역할·과정·결과가 명확(1) / 추상적·근거부족(0)\n"
         "- 일관성: 주장-근거-사례 흐름이 자연(1) / 모순·단절(0)\n"
         "- 적합성: KT/직무/질문 의도에 직접 부합(1) / 일반론·동문서답(0)\n"
         "- 논리성: 원인→행동→결과가 논리 전개(1) / 비약·누락(0)"
        ),

        # Few-shot #1 (양호)
        ("human",
         "컨텍스트 요약: OCR/NLP 경험 풍부\n키워드: OCR, OpenCV, Tesseract\n"
         "전략 영역: 경험\n질문: 성능을 어떻게 개선했나요?\n"
         "답변: OpenCV로 기울기 보정과 노이즈 제거를 추가하고, Tesseract 사전을 한글 최적화하여 "
         "인식률을 86%→94%(+8%p)로 높였습니다. 저는 전처리 파이프라인과 사전 커스터마이징을 담당했습니다."
        ),
        ("ai",
         '{{"specificity":{{"score":1,"rationale":"역할/방법/수치 명확"}},'
         '"consistency":{{"score":1,"rationale":"개선목표-방법-결과 흐름 일관"}},'
         '"fit":{{"score":1,"rationale":"질문 의도 및 OCR 직무에 직접 부합"}},'
         '"logic":{{"score":1,"rationale":"원인→개선→성과의 논리 전개"}}}}'
        ),

        # Few-shot #2 (부족)
        ("human",
         "컨텍스트 요약: OCR 초급\n키워드: 문서 인식\n"
         "전략 영역: 경험\n질문: 성능을 어떻게 개선했나요?\n"
         "답변: 열심히 하다 보니 잘 되었고 팀워크가 좋았습니다."
        ),
        ("ai",
         '{{"specificity":{{"score":0,"rationale":"수치/방법/역할 부재"}},'
         '"consistency":{{"score":0,"rationale":"목표-근거-사례 흐름 불명확"}},'
         '"fit":{{"score":0,"rationale":"질문과 직접 연결 부족"}},'
         '"logic":{{"score":0,"rationale":"원인/과정/결과 서술 없음"}}}}'
        ),

        # 실제 평가
        ("human",
         "컨텍스트 요약: {resume_summary}\n키워드: {resume_keywords}\n"
         "전략 영역: {strategy}\n질문: {question}\n답변: {answer}\n")
    ])

    chain = prompt | llm.with_structured_output(FourCriteriaEval)
    result: FourCriteriaEval = chain.invoke({
        "resume_summary": resume_ctx["summary"],
        "resume_keywords": resume_ctx["keywords"],
        "strategy": strategy,
        "question": question,
        "answer": answer
    })

    # -------------------------------------------------
    # 3. 일관성 검증 & 강제 교체 로직
    # -------------------------------------------------
    # (1) LLM이 1을 줬지만 실제 모순이 있는 경우 0으로 강제
    if result.consistency.score == 1:
        # 간단한 휴리스틱: 질문·답변에 서로 반대되는 키워드가 있으면 0
        q_lower = question.lower()
        a_lower = answer.lower()
        contradict_pairs = [
            ("아니오", "예"), ("없다", "있다"), ("실패", "성공"), ("낮다", "높다")
        ]
        if any(p in q_lower and n in a_lower or n in q_lower and p in a_lower
               for p, n in contradict_pairs):
            result.consistency.score = 0
            result.consistency.rationale = "질문과 답변에 상반되는 표현이 있어 흐름이 단절됨"

    # (2) LLM이 0을 줬다면 그대로 유지 (기본 1점에서 내려가지 않음)

    # -------------------------------------------------
    # 4. 최종 점수 저장 (조건2: 최신 덮어쓰기)
    # -------------------------------------------------
    ev = evaluation.get(strategy, {})

    ev.setdefault("_n", 0)
    ev.setdefault("_sum_구체성", 0)
    ev.setdefault("_sum_일관성", 0)
    ev.setdefault("_sum_적합성", 0)
    ev.setdefault("_sum_논리성", 0)
    ev.setdefault("question", "")
    ev.setdefault("answer", "")

    # 이번 턴 점수
    sp = int(result.specificity.score)
    co = int(result.consistency.score)
    fi = int(result.fit.score)
    lo = int(result.logic.score)

    # (선택) 첫 질문은 일관성 1점 완충을 유지하고 싶다면:
    # if ev["_n"] == 0:
    #     co = max(1, co)

    # 누적 업데이트
    ev["_n"] += 1
    ev["_sum_구체성"] += sp
    ev["_sum_일관성"] += co
    ev["_sum_적합성"] += fi
    ev["_sum_논리성"] += lo

    # 최신 스냅샷(보고서에서 최근 질/답을 참고하고 싶을 때 사용)
    ev["구체성"] = sp
    ev["일관성"] = co
    ev["적합성"] = fi
    ev["논리성"] = lo
    ev["question"] = question
    ev["answer"]  = answer

    evaluation[strategy] = ev

    conversation: List[Dict[str, str]] = state.get("conversation", [])
    conversation.append({"question": question, "answer": answer}) # (한글 바꿈 질문 질문 답변)

    state_update = {
        **state,
        "evaluation": evaluation,
        "conversation": conversation,
    }

    return state_update

def decide_next_step(state: InterviewState) -> InterviewState:
    """
    규칙 기반 진행 제어 (evaluation = {분야:{지표:점수}}):
    - 현재 분야 점수 = evaluation[cur]의 값 합 / (지표수 * max_per_dim)
    - score >= threshold → 다음 분야(next_question) 전환 + 예시 질문 랜덤 선택
    - score < threshold → 동일 분야 심화(additional_question), deep_counts[cur] += 1
    - deep_counts[cur] > 3 → 강제 다음 분야 전환(next_question)
    - 마지막 분야에서 score >= threshold → end
    """
    # 이 함수 내부에서만 쓰는 상수
    threshold = 0.75          # 통과 기준 (75%)
    max_per_dim = 1           # 각 세부 지표 만점 (예: 0~2점)

    # 분야 순서 = question_strategy의 키 순서
    qs = state.get("question_strategy", {})
    seq = list(qs.keys())
    cur = state.get("current_strategy", (seq[0] if seq else ""))
    idx = (seq.index(cur) if cur in seq else 0)

    # 평가 딕셔너리: {분야:{지표:점수}}
    ev = state.get("evaluation", {})

    # --- 현재 분야 점수 계산(정규화 0~1) ---
    cur_field_scores = ev.get(cur, {})
    crits = ("구체성", "일관성", "적합성", "논리성")

    def _safe_int(x):
        try:
            return int(x)
        except Exception:
            return 0

    if isinstance(cur_field_scores, dict) and cur_field_scores.get("_n", 0) > 0:
    # 누적 방식(_n, _sum_*) 있으면: 키워드 내 여러 답변의 평균으로 판단
        n = int(cur_field_scores["_n"])
        avg_specificity = cur_field_scores.get("_sum_구체성", 0) / n
        avg_consistency = cur_field_scores.get("_sum_일관성", 0) / n
        avg_fit        = cur_field_scores.get("_sum_적합성", 0) / n
        avg_logic      = cur_field_scores.get("_sum_논리성", 0) / n
        score = (avg_specificity + avg_consistency + avg_fit + avg_logic) / 4.0
    else:
    # 누적 키가 없으면: 스냅샷 4항목(구/일/적/논)만으로 평균
        nums = [_safe_int(cur_field_scores.get(k, 0)) for k in crits] if isinstance(cur_field_scores, dict) else [0,0,0,0]
        score = sum(nums) / 4.0

    # --- 분야별 심화 누적 카운터 관리 ---
    deep_counts = state.get("deep_counts", {})
    cur_deep = int(deep_counts.get(cur, 0))

    # if score < threshold:
    #     cur_deep += 1
    # else:
    #     pass
    # deep_counts[cur] = cur_deep

    # --- 분기 로직 ---
    if (score >= threshold) or (cur_deep >= 2):
        # 마지막 분야인지 확인
        if seq and idx >= len(seq) - 1:
            # 마지막 분야 통과 → 종료
            next_state = {**state, "next_step": "summarize", "deep_counts": deep_counts}
        else:
            # 다음 분야로 이동
            next_strategy = seq[idx + 1]

            next_state = {
                **state,
                "next_step": "change_strategy",
                "current_strategy": next_strategy,
                "deep_counts": deep_counts
            }

    else:
        # 기준 미달 → 같은 분야에서 추가 질문
        cur_deep += 1
        deep_counts[cur] = cur_deep
        next_state = {**state, "next_step": "generate", "deep_counts": deep_counts}

    # # --- 디버그 로그 ---
    # print(f"[DEBUG] 분야 순서: {seq}")
    # print(f"[DEBUG] 현재 분야: {cur} (idx={idx})")
    # print(f"[DEBUG] 세부 점수: {cur_field_scores}")
    # print(f"[DEBUG] 계산된 정규화 점수: {score:.2f} (임계값 {threshold:.2f})")
    # print(f"[DEBUG] (분야별) 심화 누적: {deep_counts}")
    # print(f"[DEBUG] 결정된 다음 단계: {next_state.get('next_step')}")
    # if next_state.get("next_step") == "next_question":
    #     print(f"[DEBUG] ▶ 다음 분야로 전환 완료: {next_state.get('current_strategy')}")
    #     print(f"[DEBUG] ▶ 제시 질문: {next_state.get('current_question')}")
    # elif next_state.get("next_step") == "summarize":
    #     print("[DEBUG] 인터뷰 종료 조건 충족")

    return next_state

def change_strategy(state: InterviewState) -> InterviewState:
    """
    decide_next_step에서 지정된 current_strategy를 기준으로,
    question_strategy의 하위 항목(A/B/C 등) 중 하나를 랜덤 선택해 current_question에 세팅.
    형식: {"경험": {"A": "...", "B": "...", "C": "..."}}
    """
    qs = state.get("question_strategy", {})
    cur = state.get("current_strategy", "")

    # 현재 분야 블록
    block = qs.get(cur, {})

    # value(질문)만 모아 랜덤 선택
    questions = [v for v in block.values() if isinstance(v, str) and v.strip()]
    selected = random.choice(questions) if questions else "다음 분야 질문을 준비 중입니다."

    #print(f"[DEBUG] ▶ 분야 확정: {cur}")
    #print(f"[DEBUG] ▶ 랜덤 선택된 질문: {selected}")

    return {
        **state,
        "current_question": selected,
        "current_answer": "",
        "next_step": ""  # 이후 루프에서 질문 제시 → 답변 입력 → 평가 단계로 이동
    }

# KT 핵심역량 및 비전

# 1. 문서 로드 (이 부분은 성공적으로 진행됨)
docx_path = os.path.join(os.path.dirname(__file__), "..", "assets", "KT.docx")
docx_loader = UnstructuredWordDocumentLoader(docx_path)
documents_doc = docx_loader.load()
full_text = "\n".join([doc.page_content for doc in documents_doc])

# 2. 텍스트 분할: RecursiveCharacterTextSplitter 사용
text_splitter = RecursiveCharacterTextSplitter(
    chunk_size=40,           # 청크 사이즈를 늘려 문맥 보존
    chunk_overlap=0,         # 오버랩을 주어 의미 연결
    separators=["\n\n", "\n"] # 다양한 구분자를 사용하여 더 의미 단위로 분할
)

split_texts = text_splitter.split_text(full_text)

# 3. 짧은 청크 제거 (Clean-up 과정)
# 너무 짧은 텍스트(예: 제목 한 줄, 띄어쓰기 한 줄 등)는 벡터 DB의 검색 정확도를 떨어뜨린다.
# 실제 핵심 내용이 담긴 청크만 남긴다. (최소 20자 이상으로 설정)
cleaned_split_texts = [text for text in split_texts if len(text.strip()) > 20]

print(f"총 {len(split_texts)}개 청크 중 {len(cleaned_split_texts)}개 유효 청크 사용")

# 4. 임베딩 & Chroma DB 생성 (유효 청크만 사용)
embeddings = GoogleGenerativeAIEmbeddings(model="models/gemini-embedding-001")
# Chroma DB는 동일한 디렉토리에 생성되므로, 실행할 때마다 새로 생성되도록 처리
# (실제 환경에서는 persist_directory를 지정하여 캐시 문제를 방지하는 것이 좋음)
vectordb = Chroma.from_texts(cleaned_split_texts, embeddings)

# KT 핵심역량에 맞는 예시 질문

# 1. 문서 로드 (이 부분은 성공적으로 진행됨)
iv_docx_path = os.path.join(os.path.dirname(__file__), "..", "assets", "KT_interview.docx")
iv_docx_loader = UnstructuredWordDocumentLoader(iv_docx_path)
iv_documents_doc = iv_docx_loader.load()
iv_full_text = "\n".join([iv_doc.page_content for iv_doc in iv_documents_doc])

# 2. 텍스트 분할: RecursiveCharacterTextSplitter 사용
text_splitter = RecursiveCharacterTextSplitter(
    chunk_size=100,           # 청크 사이즈를 늘려 문맥 보존
    chunk_overlap=50,         # 오버랩을 주어 의미 연결
    separators=["\n\n", "\n", " "] # 다양한 구분자를 사용하여 더 의미 단위로 분할
)


split_texts2 = text_splitter.split_text(iv_full_text)

# 3. 짧은 청크 제거 (Clean-up 과정)
# 너무 짧은 텍스트(예: 제목 한 줄, 띄어쓰기 한 줄 등)는 벡터 DB의 검색 정확도를 떨어뜨린다.
# 실제 핵심 내용이 담긴 청크만 남긴다. (최소 20자 이상으로 설정)
cleaned_split_texts2 = [text for text in split_texts2 if len(text.strip()) > 20]

print(f"총 {len(split_texts2)}개 청크 중 {len(cleaned_split_texts2)}개 유효 청크 사용")

# 4. 임베딩 & Chroma DB 생성 (유효 청크만 사용)
embeddings2 = GoogleGenerativeAIEmbeddings(model="models/gemini-embedding-001")
# Chroma DB는 동일한 디렉토리에 생성되므로, 실행할 때마다 새로 생성되도록 처리
# (실제 환경에서는 persist_directory를 지정하여 캐시 문제를 방지하는 것이 좋음)
vectordb2 = Chroma.from_texts(cleaned_split_texts2, embeddings2)

# LLM 출력 스키마
class DeepQuestion(BaseModel):
    question: str = Field(..., description="지원자의 사고력, 문제해결력, 기술적 깊이를 검증할 수 있는 심화 질문")

def generate_question(state: InterviewState) -> InterviewState:
    """이전 답변과 평가를 바탕으로 심화 질문을 생성"""
    question = state.get("current_question", "")
    answer = state.get("current_answer", "")
    strategy = state.get("current_strategy", "")
    resume_summary = state.get("resume_summary", "")
    keywords = ", ".join(state.get("resume_keywords", []))

    '''
    # 최근 평가 참고 (없을 경우 빈 문자열)
    last_eval = evaluations[-1] if evaluations else {}
    overall = last_eval.get("overall", "")
    rationale = "; ".join([
        f"{k}: {v.get('등급', '')}({v.get('근거', '')})"
        for k, v in last_eval.get("criteria", {}).items()
    ]) if last_eval.get("criteria") else ""
    '''

    # 최근 평가 가져오기
    evaluations = state.get("evaluation", [])

    qs = state.get("question_strategy", {})
    seq = list(qs.keys())
    cur = state.get("current_strategy", (seq[0] if seq else ""))
    ev = state.get("evaluation", {})
    last_eval = ev.get(cur, {})

    # 부족한 항목 추출 (안전하게)
    weak_points = []
    rationale_parts = []

    if isinstance(last_eval, dict):
        for category, metrics in last_eval.items():
            if isinstance(metrics, dict):
                # 0인 항목만 추출
                zero_keys = [k for k, v in metrics.items() if v == 0]
                if zero_keys:
                    weak_points.append({category: zero_keys})
                # rationale 문자열 생성
                metric_text = ", ".join([f"{k}: {v}" for k, v in metrics.items()])
                rationale_parts.append(f"{category} - {metric_text}")

    rationale = "; ".join(rationale_parts)


    # ================================
    # KT 핵심가치 확인 (similarity_search)
    docs = vectordb.similarity_search("KT 핵심가치"+answer, k=10)
    unique_docs = []
    seen_texts = set()
    for doc in docs:
        text = doc.page_content.strip()
        if text not in seen_texts:
            unique_docs.append(doc)
            seen_texts.add(text)
    # 최대 3개만 사용
    unique_docs = unique_docs[:3]

    kt_values_response = " ".join([doc.page_content for doc in unique_docs])
    kt_prompt_str = f" 답변과 관련된 KT 핵심가치: {kt_values_response}\n"

    # ================================
    # 예시질문 (similarity_search)
    docs2 = vectordb2.similarity_search(answer, k=10)
    unique_docs2 = []
    seen_texts2 = set()
    for doc2 in docs2:
        text2 = doc2.page_content.strip()
        if text2 not in seen_texts2:
            unique_docs2.append(doc2)
            seen_texts2.add(text2)
    # 최대 3개만 사용
    unique_docs2 = unique_docs2[:3]

    kt_values_response2 = " ".join([doc2.page_content for doc2 in unique_docs2])
    kt_prompt_str2 = f"지원자 답변과 관련된 KT 예상 질문: {kt_values_response2}\n"
    # ================================


    # 프롬프트 구성
    prompt = ChatPromptTemplate.from_messages([
        ("system",
        "당신은 인사담당 면접관입니다. "
        "지원자의 이전 답변을 기반으로 사고력, 문제 해결 방식, 기술적 깊이를 더 파악할 수 있는 '심화 질문'을 작성하세요. "
        "조건:\n"
        "- 한 문장으로, 자연스러운 공손체로 작성 ('~하시겠어요?', '~설명해주세요.')\n"
        "- 이전 질문과 답변 맥락을 유지하되, 새로운 관점이나 구체적 근거를 끌어낼 수 있도록 구성\n"
        "- JSON 형태로만 출력\n"
        "- kt_prompt_str과 이전 지원자 답변의 연관성이 충분하지 않으면 그냥 weak_points에 있는 부족한 항목을 중심으로만 질문해주세요.\n"
        "- kt_prompt_str과 이전 지원자 답변의 연관성이 충분하면, weak_points2를 적극 참고하여 질문해주세요.\n"
        "- 모든 질문 내용은 반드시 weak_points에 있는 부족한 항목을 중심으로 만드세요\n"),

        ("human",
        "이력서 요약: {resume_summary}\n"
        "키워드: {keywords}\n"
        "현재 전략 영역: {strategy}\n"
        "이전 질문: {question}\n"
        "지원자 답변: {answer}\n"
        "최근 평가에서 부족한 항목: {weak_points}\n"
        "KT 핵심역량: {kt_prompt_str}\\n"
        "KT 예상 질문: {kt_prompt_str2}\\n"
        "→ 위 정보를 바탕으로 한 단계 더 깊은 심화 면접 질문을 생성하세요.")
    ])

    chain = prompt | llm.with_structured_output(DeepQuestion)
    response: DeepQuestion = chain.invoke({
        "resume_summary": resume_summary,
        "keywords": keywords,
        "strategy": strategy,
        "question": question,
        "answer": answer,
        "rationale": rationale,
        "weak_points": weak_points,
        "kt_prompt_str": kt_prompt_str,
        "kt_prompt_str2": kt_prompt_str2
    })

    # return 코드는 제공합니다.
    return {
        **state,
        "current_question": response.question.strip(),
        "current_answer": ""
    }


#  최종평가 체인
final_eval_prompt = ChatPromptTemplate.from_template("""
당신은 기술 면접관입니다.
다음은 면접 질문별 요약과 평균 점수입니다.

평균 점수: {avg_score}/10
질문별 평가 요약:
{summary_for_llm}

이를 바탕으로 전체 인터뷰에 대한 종합평가를 3문장 이내로 작성하세요.
- 강점과 개선점을 모두 포함
- 객관적이고 자연스러운 평가 문체
""")
final_eval_chain = final_eval_prompt | llm | StrOutputParser()


#  인터뷰 요약 함수 - (출력: print는 프롬프트 백엔드 부분쪽에 출력되서 형식 바꿈)
def summarize_interview(state: dict):
    """AI 면접 피드백 보고서를 Gradio에서 표시 가능한 문자열 형태로 반환"""
    evaluations = state.get("evaluation", {})
    order = list(state.get("question_strategy", {}).keys()) if isinstance(state.get("question_strategy", {}), dict) else ["경험","동기","논리"]

    # 문자열 누적 변수
    report = ""
    report += "============================================================\n"
    report += " [AI 면접 피드백 보고서]\n"
    report += "============================================================\n"

    if not evaluations:
        report += " 평가 내역이 없습니다.\n"
        report += "============================================================\n"
        state["next_step"] = "end"
        state["final_report"] = report
        return state

    crits = ["구체성", "일관성", "적합성", "논리성"]
    total_scores = []
    summary_for_llm_lines = []

    for s in order:
        ev = evaluations.get(s, {})
        n = int(ev.get("_n", 0))

        if n > 0:
            avg = {
                "구체성": ev.get("_sum_구체성", 0) / n,
                "일관성": ev.get("_sum_일관성", 0) / n,
                "적합성": ev.get("_sum_적합성", 0) / n,
                "논리성": ev.get("_sum_논리성", 0) / n,
            }
        else:
            avg = {k: float(ev.get(k, 0)) for k in crits}
            if sum(avg.values()) == 0:
                continue
            n = 1

        overall = round((sum(avg.values()) / 4) * 10)
        total_scores.append(overall)
        strengths = [k for k, v in avg.items() if v >= 0.75]
        weaknesses = [k for k, v in avg.items() if v < 0.5]

        report += f"\n[{s}] 종합 평가 (질문 {n}개 기반)\n"
        report += "------------------------------------------------------------\n"
        report += " 항목별 평균(0~1): " + ", ".join([f"{k} {avg[k]:.2f}" for k in crits]) + "\n"
        report += f" ▶ 종합 점수: {overall}/10\n"
        if strengths:
            report += f" ▶ 강점: {', '.join(strengths)}\n"
        if weaknesses:
            report += f" ▶ 개선 필요: {', '.join(weaknesses)}\n"

        if s == "경험":
            report += " ▸ 조언: 수치·역할·방법을 STAR(상황-과제-행동-결과) 구조로 일관되게 제시하세요.\n"
        elif s == "동기":
            report += " ▸ 조언: ‘왜 우리/왜 지금/왜 나’를 2~3문장 핵심 연결로 선명하게 설명하세요.\n"
        elif s == "논리":
            report += " ▸ 조언: 원인→대안→선택 근거→결과의 인과 뼈대를 먼저 말하고 사례를 덧붙이세요.\n"

        summary_for_llm_lines.append(
            f"- {s}: 종합 {overall}/10 | 평균(구체성 {avg['구체성']:.2f}, 일관성 {avg['일관성']:.2f}, 적합성 {avg['적합성']:.2f}, 논리성 {avg['논리성']:.2f})"
        )

    if total_scores:
        avg_score = round(sum(total_scores) / len(total_scores))
        report += "\n [인터뷰 전체 종합 평가]\n"
        report += "============================================================\n"
        report += f" 평균 점수: {avg_score}/10\n\n"

        final_feedback = final_eval_chain.invoke({
            "avg_score": avg_score,
            "summary_for_llm": "\n".join(summary_for_llm_lines)
        })
        report += f" {final_feedback}\n"
    else:
        report += "\n 종합 점수를 계산할 수 있는 평가 데이터가 부족합니다.\n"

    report += "============================================================\n"
    report += " 인터뷰가 종료되었습니다. 수고하셨습니다!\n"

    # state에 저장 (Gradio에서 표시)
    state["next_step"] = "end"
    state["final_report"] = report
    return state

# 분기 판단 함수
def route_next(state: InterviewState) -> Literal["generate", "change_strategy", "summarize"]:
    step = state.get("next_step", "additional_question")
    if step == "summarize" or step == "end":
        return "summarize"
    elif step == "change_strategy":
        return "change_strategy"
    else:
        return "generate"


# 내부 노드: 사용자 답변을 state에 반영 (임시 키 'incoming_answer' 사용)??
def _update_answer_node(state: InterviewState) -> InterviewState:
    user_answer = state.get("current_answer", "")
    new_state = update_current_answer(state, user_answer)
    if "current_answer" in new_state:
        new_state.pop("current_answer")
    return new_state


# 그래프 정의 시작
builder = StateGraph(InterviewState)

# 노드 추가
builder.add_node("update_answer", _update_answer_node)
builder.add_node("evaluate", evaluate_answer)
builder.add_node("decide", decide_next_step)
builder.add_node("generate", generate_question)
builder.add_node("change_strategy", change_strategy)
builder.add_node("summarize", summarize_interview)

# 노드 연결
builder.set_entry_point("update_answer")
builder.add_edge("update_answer", "evaluate")
builder.add_edge("evaluate", "decide")
builder.add_conditional_edges(
    "decide",
    route_next,
    {
        "generate": "generate",
        "change_strategy" : "change_strategy",
        "summarize": "summarize",
    }
)
builder.add_edge("generate", END)
builder.add_edge("change_strategy", END)
builder.add_edge("summarize", END)

# 컴파일
graph = builder.compile()
