import argparse
import hashlib
import json
import re
from pathlib import Path

import fitz


BASE_DIR = Path(__file__).resolve().parent
PDF_PATH = BASE_DIR / "assets" / "interview_questions.pdf"
PREVIEW_PATH = BASE_DIR / "data" / "interview_questions_preview.json"

CHROMA_DIR = BASE_DIR / "data" / "chroma_interview_ko"
COLLECTION_NAME = "interview_questions"
MODEL_NAME = "jhgan/ko-sroberta-multitask"


def extract_questions():
    """PDF에서 질문 후보를 추출하고 확인용 JSON으로 저장한다."""
    if not PDF_PATH.is_file():
        raise FileNotFoundError(f"PDF 파일이 없습니다: {PDF_PATH}")

    questions = []
    current_lines = []
    start_page = 0

    def save_current():
        if current_lines:
            text = re.sub(r"\s+", " ", " ".join(current_lines)).strip()
            if text:
                questions.append({
                    "text": text,
                    "page": start_page,
                })
            current_lines.clear()

    with fitz.open(PDF_PATH) as pdf:
        for page_no, page in enumerate(pdf, start=1):
            for raw_line in page.get_text().splitlines():
                line = raw_line.strip()

                if not line:
                    continue

                # 반복 머리말·꼬리말·페이지 번호 제외
                if (
                    re.fullmatch(r"\d+", line)
                    or "면접 기출질문 자료집" in line
                    or "면접기출질문" in line
                    or line == "해커스잡"
                ):
                    continue

                # 기업·그룹 제목에서 이전 질문을 마무리한다.
                if re.match(r"^(?:\d+\.\s+|[①-⑳]\s*)", line):
                    save_current()
                    continue

                bullet = re.match(r"^[-•●]\s*(.*)", line)

                if bullet:
                    save_current()
                    start_page = page_no
                    current_lines.append(bullet.group(1))
                elif current_lines:
                    # 줄바꿈으로 나뉜 질문을 연결한다.
                    current_lines.append(line)

        save_current()

    # 동일한 질문은 한 번만 남긴다.
    unique = {}
    for item in questions:
        unique.setdefault(item["text"], item)

    records = list(unique.values())

    if not records:
        raise ValueError(
            "질문이 추출되지 않았습니다. PDF의 텍스트·글머리표 형식을 확인하세요."
        )

    PREVIEW_PATH.parent.mkdir(parents=True, exist_ok=True)
    PREVIEW_PATH.write_text(
        json.dumps(records, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"추출한 질문 후보: {len(records)}개")
    print(f"확인할 파일: {PREVIEW_PATH}")
    print("질문 누락·광고·기업 제목 혼입 등을 확인하고 수정하세요.")


def build_db():
    """검토한 JSON을 로컬 모델로 임베딩하고 Chroma에 적재한다."""
    import chromadb
    from langchain_core.documents import Document
    from langchain_huggingface import HuggingFaceEmbeddings
    from langchain_text_splitters import RecursiveCharacterTextSplitter
    from transformers import AutoTokenizer

    if not PREVIEW_PATH.is_file():
        raise FileNotFoundError("먼저 질문 추출 명령을 실행하세요.")

    records = json.loads(PREVIEW_PATH.read_text(encoding="utf-8"))

    if not isinstance(records, list) or not records:
        raise ValueError("확인용 JSON에 질문 목록이 없습니다.")

    documents = []
    for index, item in enumerate(records, start=1):
        text = item["text"].strip()
        if not text:
            continue

        documents.append(Document(
            page_content=text,
            metadata={
                "source": PDF_PATH.name,
                "page": int(item["page"]),
                "question_no": index,
            },
        ))

    if not documents:
        raise ValueError("적재할 질문이 없습니다.")

    # 짧은 질문은 그대로 유지하고, 긴 질문만 모델 입력 길이에 맞게 분할한다.
    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
    splitter = RecursiveCharacterTextSplitter.from_huggingface_tokenizer(
        tokenizer,
        chunk_size=110,
        chunk_overlap=15,
        separators=["\n\n", "\n", ". ", "? ", " ", ""],
    )
    chunks = splitter.split_documents(documents)

    # 같은 텍스트는 같은 ID를 갖도록 한다.
    chunks_by_id = {}
    for chunk in chunks:
        doc_id = hashlib.sha256(
            chunk.page_content.encode("utf-8")
        ).hexdigest()
        chunks_by_id.setdefault(doc_id, chunk)

    client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    collection = client.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"embedding_model": MODEL_NAME},
    )

    if (collection.metadata or {}).get("embedding_model") != MODEL_NAME:
        raise ValueError("기존 컬렉션의 임베딩 모델이 다릅니다.")

    existing_ids = set(collection.get(include=[])["ids"])
    pending = [
        (doc_id, chunk)
        for doc_id, chunk in chunks_by_id.items()
        if doc_id not in existing_ids
    ]

    if not pending:
        print(f"추가할 자료가 없습니다. 현재 DB: {collection.count()}건")
        return

    embeddings = HuggingFaceEmbeddings(
        model_name=MODEL_NAME,
        model_kwargs={"device": "cpu"},
        encode_kwargs={"normalize_embeddings": True},
    )

    batch_size = 32
    for start in range(0, len(pending), batch_size):
        batch = pending[start:start + batch_size]
        texts = [chunk.page_content for _, chunk in batch]

        collection.add(
            ids=[doc_id for doc_id, _ in batch],
            documents=texts,
            metadatas=[chunk.metadata for _, chunk in batch],
            embeddings=embeddings.embed_documents(texts),
        )

        print(f"적재: {min(start + batch_size, len(pending))}/{len(pending)}")

    print(f"완료: 현재 DB에 {collection.count()}건 저장")
    print(f"저장 위치: {CHROMA_DIR}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--build",
        action="store_true",
        help="검토한 JSON을 임베딩하고 DB에 적재",
    )
    args = parser.parse_args()

    if args.build:
        build_db()
    else:
        extract_questions()