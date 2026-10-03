import { useEffect, useState } from "react"
import { api } from "../api"

// 생성일 문자열("2026-10-03 23:19:09...")을 "2026.10.03" 로 정리
function fmtDate(s) {
  if (!s) return ""
  const d = String(s).slice(0, 10).replaceAll("-", ".")
  return d
}

// 파일 확장자 느낌의 아이콘 라벨 (백엔드엔 원본 파일명이 없어 DOC로 통일 표기)
export default function Home({ user, onNew, onStart }) {
  const [resumes, setResumes] = useState(null) // null=로딩중
  const [error, setError] = useState("")
  const [startingId, setStartingId] = useState(null)

  async function load() {
    setError("")
    try {
      const list = await api.listResumes()
      setResumes(list)
    } catch (err) {
      setError(err.message)
      setResumes([])
    }
  }

  useEffect(() => {
    load()
  }, [])

  async function start(resume) {
    setStartingId(resume.id)
    setError("")
    try {
      await onStart(resume)
    } catch (err) {
      setError(err.message)
      setStartingId(null)
    }
  }

  async function remove(id) {
    if (!confirm("이 문서를 삭제할까요?")) return
    try {
      await api.deleteResume(id)
      load()
    } catch (err) {
      setError(err.message)
    }
  }

  return (
    <div className="page">
      <div className="home-top">
        <div className="page-head">
          <h1>{user.name}님, 오늘도 연습해볼까요?</h1>
          <p>저장된 문서로 바로 시작하거나, 새 문서를 올려 면접을 준비하세요.</p>
        </div>
        <button className="btn btn-primary" onClick={onNew}>
          + 새 면접 시작
        </button>
      </div>

      <div className="home-grid">
        <div className="card panel">
          <div className="panel-head">
            <h3>저장된 문서</h3>
            <span className="hint">선택해서 바로 면접 시작</span>
          </div>

          {resumes === null && <div className="empty">불러오는 중…</div>}

          {resumes && resumes.length === 0 && (
            <div className="empty">
              저장된 문서가 없어요.
              <br />
              “새 면접 시작”에서 이력서를 올려보세요.
            </div>
          )}

          {resumes &&
            resumes.map((r) => (
              <div className="doc-row" key={r.id}>
                <div className="doc-icon">DOC</div>
                <div className="doc-main">
                  <div className="doc-title">{r.title}</div>
                  <div className="doc-meta">
                    {[r.company, r.position].filter(Boolean).join(" · ")}
                    {(r.company || r.position) && r.created_at ? " · " : ""}
                    {fmtDate(r.created_at)} 업로드
                  </div>
                </div>
                <div className="doc-actions">
                  <button
                    className="btn btn-sm"
                    onClick={() => start(r)}
                    disabled={startingId === r.id}
                  >
                    {startingId === r.id ? "준비 중…" : "이 문서로 면접"}
                  </button>
                  <button className="btn btn-sm btn-ghost-danger" onClick={() => remove(r.id)}>
                    삭제
                  </button>
                </div>
              </div>
            ))}

          {error && <div className="error-text">{error}</div>}
        </div>
      </div>
    </div>
  )
}
