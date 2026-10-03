import { useEffect, useRef, useState } from "react"
import { api } from "../api"

// 면접 준비: 새 문서 업로드 또는 저장된 문서 선택 → 면접 시작
export default function Prep({ onStart, onHome }) {
  const [mode, setMode] = useState("upload") // upload | saved
  const [title, setTitle] = useState("")
  const [company, setCompany] = useState("")
  const [position, setPosition] = useState("")
  const [file, setFile] = useState(null)
  const fileRef = useRef(null)

  const [resumes, setResumes] = useState([])
  const [selectedId, setSelectedId] = useState(null)

  const [loading, setLoading] = useState(false)
  const [error, setError] = useState("")

  useEffect(() => {
    if (mode === "saved") {
      api
        .listResumes()
        .then(setResumes)
        .catch((err) => setError(err.message))
    }
  }, [mode])

  // 업로드 모드에서 면접 시작 가능 여부
  const uploadReady = title.trim() && company.trim() && position.trim() && file
  const ready = mode === "upload" ? uploadReady : !!selectedId

  async function start() {
    setError("")
    setLoading(true)
    try {
      let resume
      if (mode === "upload") {
        resume = await api.uploadResume(title.trim(), company.trim(), position.trim(), file)
      } else {
        resume = resumes.find((r) => r.id === selectedId)
      }
      await onStart(resume)
    } catch (err) {
      setError(err.message)
      setLoading(false)
    }
  }

  return (
    <div className="page">
      <div className="page-head">
        <h1>면접 준비</h1>
        <p>
          AI 면접관이 참고할 이력서와 지원 정보를 입력하세요. 입력한 기업·직무에 맞춰
          면접관 역할과 평가 기준이 정해집니다.
        </p>
      </div>

      <div className="prep-grid">
        <div>
          <div className="seg">
            <button className={mode === "upload" ? "active" : ""} onClick={() => setMode("upload")}>
              새로 업로드
            </button>
            <button className={mode === "saved" ? "active" : ""} onClick={() => setMode("saved")}>
              저장된 문서 불러오기
            </button>
          </div>

          {mode === "upload" && (
            <div className="card" style={{ padding: 24 }}>
              <div className="field">
                <label>
                  이력서 파일<span className="badge badge-req">필수</span>
                </label>
                <div
                  className="upload-box drop card"
                  style={{ boxShadow: "none" }}
                  onClick={() => fileRef.current?.click()}
                >
                  <div className="upload-plus">+</div>
                  <div className="upload-main">
                    <div className="t">
                      {file ? <span className="file-name">{file.name}</span> : "파일 선택 또는 끌어다 놓기"}
                    </div>
                    <div className="d">학력·경력·프로젝트 경험이 담긴 PDF 또는 DOCX</div>
                  </div>
                  <input
                    ref={fileRef}
                    type="file"
                    accept=".pdf,.docx"
                    style={{ display: "none" }}
                    onChange={(e) => setFile(e.target.files[0])}
                  />
                </div>
              </div>

              <div className="field">
                <label>문서 제목</label>
                <input
                  type="text"
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  placeholder="예: 네이버 지원용 이력서"
                />
              </div>

              <div style={{ display: "flex", gap: 14 }}>
                <div className="field" style={{ flex: 1 }}>
                  <label>지원 기업</label>
                  <input
                    type="text"
                    value={company}
                    onChange={(e) => setCompany(e.target.value)}
                    placeholder="예: 네이버"
                  />
                </div>
                <div className="field" style={{ flex: 1 }}>
                  <label>지원 직무</label>
                  <input
                    type="text"
                    value={position}
                    onChange={(e) => setPosition(e.target.value)}
                    placeholder="예: AI 엔지니어"
                  />
                </div>
              </div>

              <div className="prep-note">
                PDF, DOCX 지원 · 업로드한 문서는 내 계정에 저장되어 다음 면접에서 다시 불러올 수 있습니다.
              </div>
            </div>
          )}

          {mode === "saved" && (
            <div className="card" style={{ padding: 8 }}>
              {resumes.length === 0 && <div className="empty">저장된 문서가 없습니다.</div>}
              {resumes.map((r) => (
                <label
                  className="doc-row"
                  key={r.id}
                  style={{ padding: "14px 16px", cursor: "pointer" }}
                >
                  <input
                    type="radio"
                    name="saved"
                    checked={selectedId === r.id}
                    onChange={() => setSelectedId(r.id)}
                    style={{ accentColor: "var(--accent)" }}
                  />
                  <div className="doc-main">
                    <div className="doc-title">{r.title}</div>
                    <div className="doc-meta">{[r.company, r.position].filter(Boolean).join(" · ")}</div>
                  </div>
                </label>
              ))}
            </div>
          )}

          {error && <div className="error-text">{error}</div>}
        </div>

        <div className="card side-card">
          <h3>면접 방식</h3>
          <ol className="howto">
            <li>
              <span className="n">1</span>
              AI가 문서를 읽고 첫 질문을 만듭니다.
            </li>
            <li>
              <span className="n">2</span>
              답변을 입력하면 그 내용을 바탕으로 꼬리 질문이 이어집니다.
            </li>
            <li>
              <span className="n">3</span>
              면접을 마치면 항목별 분석 리포트가 생성됩니다.
            </li>
          </ol>

          <div className="side-status">
            <span className="label">{mode === "upload" ? "입력 상태" : "선택된 문서"}</span>
            <span className="val">{ready ? "준비 완료" : "미완료"}</span>
          </div>

          <button className="btn btn-primary btn-block" disabled={!ready || loading} onClick={start}>
            {loading ? "면접 준비 중…" : "면접 시작하기"}
          </button>
          {!ready && (
            <div className="side-hint">
              {mode === "upload" ? "이력서·제목·기업·직무를 모두 입력하면 시작할 수 있어요" : "문서를 선택하면 시작할 수 있어요"}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
