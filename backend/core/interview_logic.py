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

from functools import lru_cache
from pathlib import Path

import chromadb
from langchain_chroma import Chroma
from langchain_huggingface import HuggingFaceEmbeddings

from langgraph.graph import StateGraph, START, END
from typing import TypedDict, List, Dict
from pydantic import BaseModel, Field
from typing import List
from tabulate import tabulate
import tempfile

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


# 기업·직무를 입력받지 못했을 때 쓰는 기본값.
DEFAULT_COMPANY = "지원 기업"
DEFAULT_POSITION = "지원 직무"


class InterviewState(TypedDict, total=False):
    # 고정 정보
    resume_text: str
    resume_summary: str
    resume_keywords: List[str]
    company: str                 # 지원 기업명 (면접관 페르소나 구성에 사용)
    position: str                # 지원 직무명
    question_strategy: Dict[str, Dict[str, str]]

    # 인터뷰 로그
    current_question: str
    current_answer: str
    current_strategy: str
    conversation: List[Dict[str, str]]
    # {영역: {지표: 점수, question, answer, _n, _sum_지표...}} 형태의 2층 딕셔너리.
    evaluation: Dict[str, Dict[str, object]]
    next_step: str
    deep_counts: Dict[str, int]  # {영역: 심화질문 누적 횟수}
    final_report: str            # summarize_interview() 가 마지막에 채운다



# LLM 출력 형식 (pydantic 모델)
class ResumeAnalysis(BaseModel):
    summary: str = Field(..., description="이력서 주요 내용을 3~5문장으로 요약한 문장")
    keywords: List[str] = Field(..., description="이력서의 핵심 역량 및 키워드 목록")

# llm 모델 정의
llm = ChatGoogleGenerativeAI(model="gemini-3.5-flash-lite")

def analyze_resume(state: InterviewState) -> InterviewState:
  '''
  이력서를 분석해 핵심을 요약하고 주요 키워드를 추출
  '''
  # 1. 이력서 텍스트 가져오기
  resume_text = state["resume_text"]

  company = state.get("company") or DEFAULT_COMPANY
  position = state.get("position") or DEFAULT_POSITION

  # 2. 프롬프트 구성
  prompt_template = ChatPromptTemplate.from_messages([
      ("system",
        "당신은 {company}의 {position} 직무 인사담당자입니다. "
        "다음 이력서 텍스트를 분석하여 핵심 요약과 주요 키워드를 도출하세요. "
        "해당 직무와의 관련성이 높은 내용을 우선해서 뽑으세요. "
        "결과는 JSON 형태로 반환하세요. "
        "1. summary: 이력서 핵심 요약 (3~5문장) "
        "2. keywords: 주요 키워드 목록 (핵심 역량, 기술, 성과, 강점 등)"),
      ("human", "분석할 이력서 텍스트:\n---\n{resume_text}")
  ])

  # 3. LLM 실행 (Pydantic 구조화 출력)
  chain = prompt_template | llm.with_structured_output(ResumeAnalysis)
  result: ResumeAnalysis = chain.invoke({
      "resume_text": resume_text,
      "company": company,
      "position": position,
  })

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
    company = state.get("company") or DEFAULT_COMPANY
    position = state.get("position") or DEFAULT_POSITION

    prompt = ChatPromptTemplate.from_messages([
        ("system",
         "당신은 {company}의 {position} 직무 채용을 담당하는 시니어 면접관입니다.\n"
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
        "keywords": ", ".join(keywords) if isinstance(keywords, list) else str(keywords),
        "company": company,
        "position": position,
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


def preProcessing_Interview(
    file_path: str,
    company: str = "",
    position: str = "",
) -> InterviewState:
    """이력서 파일 경로 입력 → 텍스트 추출 후 처리"""
    resume_text = extract_text_from_file(file_path)
    return preProcessing_Interview_from_text(resume_text, company, position)


def preProcessing_Interview_from_text(
    resume_text: str,
    company: str = "",
    position: str = "",
) -> InterviewState:
    """이력서 텍스트 + 지원 기업/직무 입력 → 분석 → 질문전략 생성 → 첫 질문 선택"""

    # 초기 state 설정
    # evaluation 은 {영역: {지표: 점수}} 형태로 쓰이므로 처음부터 딕셔너리로 둔다.
    state: InterviewState = {
        "resume_text": resume_text,
        "resume_summary": "",
        "resume_keywords": [],
        "company": (company or "").strip() or DEFAULT_COMPANY,
        "position": (position or "").strip() or DEFAULT_POSITION,
        "question_strategy": {},
        "current_question": "",
        "current_answer": "",
        "current_strategy": "",
        "conversation": [],
        "evaluation": {},
        "next_step": "",
        "deep_counts": {},
        "final_report": "",
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


# 평가 지표 4종. evaluation[영역] 안에는 이 4개 키 외에
# question / answer / _n / _sum_* 같은 메타 키가 함께 들어 있으므로,
# 점수를 읽을 때는 반드시 이 목록만 순회해야 한다.
CRITERIA = ("구체성", "일관성", "적합성", "논리성")


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


# ===== 메인: 평가 + 라우팅(조건1/2) + few-shot 프롬프트 =====
def evaluate_answer(state: Dict) -> Dict:
    state = _ensure_state_schema(state)

    question = state.get("current_question", "")
    answer   = state.get("current_answer", "")
    strategy = state.get("current_strategy", "기본")
    company  = state.get("company") or DEFAULT_COMPANY
    position = state.get("position") or DEFAULT_POSITION
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
        ("system", """
        너는 {company}의 {position} 직무 면접관이다.
        다음 네 항목을 서로 독립적으로 0 또는 1로 채점하라.

        평가 공통 지침:
        - 먼저 질문에서 무엇을 설명하거나 판단하도록 요구했는지 파악한다.
        - 관련 주제를 언급했더라도 질문의 핵심 요구에 답하지 않았다면 적합성은 0점으로 평가한다.
        - 구체성과 논리성은 질문이 요구한 설명의 범위 안에서 평가한다. 질문과 무관한 상세 설명이나 답변의 길이만으로 점수를 주지 않는다.
        - 방법을 물었는데 결과만 답했다면, 행동·방법의 구체성이 충족됐다고 판단하지 않는다.
        - 각 항목은 독립적으로 평가한다. 적합성이 0점이라는 이유로 나머지 항목을 일괄 0점 처리하지 않는다.
        - 질문이 요구하지 않은 정보가 없다는 이유로 감점하지 않는다. 모든 답변에 수치나 상황·행동·결과 전체를 요구하지 않는다.
        - 현재 답변에 명시된 내용만 채점 근거로 사용한다. 이력서 요약은 배경 이해에만 사용하고, 빠진 설명을 이력서나 일반 지식으로 보충하지 않는다.
        - 각 항목의 1점 조건이 확인될 때만 1점을 부여한다. 확인에 필요한 설명이 부족하면 0점을 부여한다.
        - 제공되지 않은 기업 인재상이나 채용 기준을 추정하지 않는다.

        평가 항목:
        - 구체성: 질문에서 요구한 경험·행동·방법·이유 등을 실제 내용을 파악할 수 있을 정도로 설명하면 1. 행동이나 방법을 묻는 질문에서는 무엇을 대상으로 어떻게 했는지 확인한다. '분석했다', '개선했다', '협업했다'처럼 활동 이름만 제시하거나 본인의 역할을 물었는데 팀 전체 성과만 제시하면 0. 수치나 기술명만으로 1점을 주지 않으며, 수치가 없어도 필요한 설명이 구체적이면 1점을 줄 수 있다.
        - 일관성: 답변 안의 진술이 서로 모순되지 않으면 1. 동일한 대상·시점·조건에 대해 양립할 수 없는 진술이 있으면 0. 시간 경과나 행동에 따른 변화는 그 자체로 모순으로 판단하지 않는다.
        - 적합성: 질문의 핵심 요구에 직접 답하면 1. 관련 주제만 언급하거나 핵심 요구에 답하지 않으면 0. 직무 관련성을 묻는 질문에서는 입력된 지원 직무와의 연결도 확인한다.
        - 논리성: 질문에서 요구한 주장·판단·행동을 뒷받침하는 이유나 근거가 있고, 그 연결이 설명되면 1. 근거 없이 결론만 제시하거나 결과가 좋았다는 말로 방법의 타당성을 대신하면 0. 설명되지 않은 연결 관계를 추측해서 보완하지 않는다. 인과관계를 묻는 질문에서는 행동과 결과를 연결하는 근거도 확인한다.

        출력:
        각 항목은 score(0 또는 1)와 rationale(1~2문장)로 반환한다.
        rationale에는 질문의 요구와 답변에서 충족하거나 누락한 내용을 구체적으로 명시한다.
        """),

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
         '"consistency":{{"score":1,"rationale":"답변 내부에 상충하는 진술은 없음"}},'
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
        "answer": answer,
        "company": company,
        "position": position,
    })


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
    현재 분야의 누적 평균 점수와 심화 질문 횟수로 다음 단계를 결정한다.

    - 누적 평균 = 현재 분야의 누적 점수 합 / (답변 수 * 4)
    - 누적 평균이 0.75 이상이거나 심화 질문을 이미 2회 진행한 경우:
      다음 분야가 있으면 current_strategy를 변경하고
      next_step을 "change_strategy"로 설정한다.
      마지막 분야이면 next_step을 "summarize"로 설정한다.
    - 그 외에는 심화 질문 횟수를 1 증가시키고
      next_step을 "generate"로 설정한다.

    다음 질문 선택과 리포트 생성은 각 후속 노드에서 수행한다.
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

# 문서 적재 스크립트에서도 같은 설정을 사용해야 한다.
EMBEDDING_MODEL_NAME = "jhgan/ko-sroberta-multitask"
CHROMA_DIR = (
    Path(__file__).resolve().parents[1]
    / "data"
    / "chroma_interview_ko"
)
CHROMA_COLLECTION_NAME = "interview_questions"


@lru_cache(maxsize=1)
def get_interview_vectordb():
    if not CHROMA_DIR.is_dir():
        raise RuntimeError(
            f"면접 질문 DB가 없습니다. 먼저 자료를 적재하세요: {CHROMA_DIR}"
        )

    client = chromadb.PersistentClient(path=str(CHROMA_DIR))

    # 존재하는 컬렉션만 읽는다.
    # 컬렉션명 오류를 숨기기 위해 빈 컬렉션을 새로 만들지 않는다.
    collection = client.get_collection(
        name=CHROMA_COLLECTION_NAME
    )

    if collection.count() == 0:
        raise RuntimeError("면접 질문 DB에 저장된 자료가 없습니다.")

    embeddings = HuggingFaceEmbeddings(
        model_name=EMBEDDING_MODEL_NAME,
        model_kwargs={"device": "cpu"},
        encode_kwargs={"normalize_embeddings": True},
    )

    return Chroma(
        client=client,
        collection_name=CHROMA_COLLECTION_NAME,
        embedding_function=embeddings,
    )

# LLM 출력 스키마
class DeepQuestion(BaseModel):
    question: str = Field(..., description="지원자의 사고력, 문제해결력, 기술적 깊이를 검증할 수 있는 심화 질문")

def generate_question(state: InterviewState) -> InterviewState:
    """답변 평가 결과와 국내 면접 질문 자료를 참고해 심화 질문을 생성한다."""

    question = state.get("current_question", "")
    answer = state.get("current_answer", "")
    strategy = state.get("current_strategy", "")
    resume_summary = state.get("resume_summary", "")
    keywords = ", ".join(state.get("resume_keywords", []))
    company = state.get("company") or DEFAULT_COMPANY
    position = state.get("position") or DEFAULT_POSITION

    # 가장 최근 답변에서 0점을 받은 평가 항목을 찾는다.
    evaluations = state.get("evaluation", {})
    last_eval = evaluations.get(strategy, {})

    weak_points = [
        name
        for name in CRITERIA
        if last_eval.get(name) == 0
    ]

    score_summary = ", ".join(
        f"{name}: {last_eval[name]}"
        for name in CRITERIA
        if name in last_eval
    )

    # 누적 평균 때문에 심화 경로로 왔지만,
    # 최신 답변에는 0점 항목이 없는 경우도 처리한다.
    focus = (
        ", ".join(weak_points)
        if weak_points
        else "본인 역할, 행동의 근거, 결과 확인"
    )

    # 검색에만 짧은 질문·답변을 사용한다.
    # 아래 질문 생성 프롬프트에는 전체 내용을 전달한다.
    query = (
        f"면접 분야: {strategy}\n"
        f"확인할 내용: {focus}\n"
        f"현재 질문: {question[:80]}\n"
        f"답변 핵심: {answer[:120]}"
    )

    vectordb = get_interview_vectordb()
    docs = vectordb.similarity_search(query, k=3)

    # 검색 결과의 중복 텍스트 제거
    reference_texts = list(
        dict.fromkeys(
            doc.page_content.strip()
            for doc in docs
            if doc.page_content.strip()
        )
    )

    reference_questions = "\n\n".join(reference_texts)

    prompt = ChatPromptTemplate.from_messages([
        (
            "system",
            "당신은 {company}의 {position} 직무 면접관입니다. "
            "지원자의 이전 답변을 바탕으로 심화 질문 하나를 작성하세요.\n"
            "조건:\n"
            "- 한 문장으로 자연스러운 공손체로 작성하세요.\n"
            "- 현재 면접 분야와 이전 질문·답변의 맥락을 유지하세요.\n"
            "- 부족한 평가 항목이 있으면 해당 내용을 추가로 확인하세요.\n"
            "- 부족한 항목이 비어 있으면 답변에서 더 확인할 가치가 "
            "있는 내용을 질문하세요.\n"
            "- 참고자료는 질문 방식과 확인할 내용을 참고하는 "
            "용도로만 사용하세요.\n"
            "- 자료 속 기업명, 제품명, 개인 경험을 지원자의 "
            "정보로 옮기지 마세요.\n"
            "- 현재 질문과 답변에서 이미 확인된 내용을 반복하지 마세요.\n"
            "- 관련 있는 참고자료가 없으면 현재 질문과 답변을 "
            "근거로 질문하세요.\n"
            "- 제공되지 않은 기업 인재상이나 채용 기준을 추정하지 마세요.\n"
            "- 결과는 지정된 JSON 형식으로만 반환하세요."
        ),
        (
            "human",
            "이력서 요약: {resume_summary}\n"
            "핵심 키워드: {keywords}\n"
            "현재 면접 분야: {strategy}\n"
            "이전 질문: {question}\n"
            "지원자 답변: {answer}\n"
            "부족한 평가 항목: {weak_points}\n"
            "최근 답변의 평가 점수: {score_summary}\n\n"
            "참고자료(국내 면접 질문 예시):\n"
            "{reference_questions}\n\n"
            "위 내용을 바탕으로 심화 질문 하나를 작성하세요."
        ),
    ])

    chain = prompt | llm.with_structured_output(DeepQuestion)

    response: DeepQuestion = chain.invoke({
        "company": company,
        "position": position,
        "resume_summary": resume_summary,
        "keywords": keywords,
        "strategy": strategy,
        "question": question,
        "answer": answer,
        "weak_points": weak_points,
        "score_summary": score_summary,
        "reference_questions": reference_questions,
    })

    return {
        **state,
        "current_question": response.question.strip(),
        "current_answer": "",
    }

#  최종평가 체인
final_eval_prompt = ChatPromptTemplate.from_template("""
당신은 {company}의 {position} 직무 면접관입니다.
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
            "summary_for_llm": "\n".join(summary_for_llm_lines),
            "company": state.get("company") or DEFAULT_COMPANY,
            "position": state.get("position") or DEFAULT_POSITION,
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


# 내부 노드: 그래프 진입 시 들어온 사용자 답변을 정규화(공백 제거)해서 state에 반영.
# 다음 노드인 evaluate_answer()가 current_answer를 읽으므로 이 키를 제거하면 안 된다.
# (LangGraph는 반환 dict에 없는 키를 삭제하지 않고 이전 값을 유지하므로 그래프 경로에서는
#  증상이 드러나지 않지만, 노드를 직접 이어 붙이면 빈 문자열이 평가된다.)
def _update_answer_node(state: InterviewState) -> InterviewState:
    user_answer = state.get("current_answer", "")
    return update_current_answer(state, user_answer)


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