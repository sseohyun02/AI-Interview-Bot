import { useState } from "react"
import { api, setToken } from "../api"

// 좌측 다크 패널 + 우측 로그인/회원가입 폼
export default function Auth({ onAuthed }) {
  const [tab, setTab] = useState("login") // login | register
  const [name, setName] = useState("")
  const [email, setEmail] = useState("")
  const [password, setPassword] = useState("")
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState("")

  async function submit(e) {
    e.preventDefault()
    setError("")
    setLoading(true)
    try {
      if (tab === "register") {
        await api.register(name.trim(), email.trim(), password)
      }
      // 회원가입 후에도 바로 로그인해서 토큰 발급
      const res = await api.login(email.trim(), password)
      setToken(res.access_token)
      const me = await api.me()
      onAuthed(me)
    } catch (err) {
      setError(err.message || "오류가 발생했습니다.")
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="auth">
      <div className="auth-left">
        <div className="brand">
          <span className="logo-mark" />
        </div>

        <div className="hero">
          <h1>
            내 이력서를 읽은 AI
            <br />
            면접관과 실전처럼
            <br />
            연습하세요
          </h1>
          <p>
            이력서를 바탕으로 질문하고, 답변에 따라 꼬리 질문을 이어갑니다.
            면접이 끝나면 항목별 분석 리포트를 받아볼 수 있어요.
          </p>
        </div>

        <div className="auth-steps">
          <div className="step">
            <div className="num">01</div>
            <div className="label">문서 업로드</div>
          </div>
          <div className="step">
            <div className="num">02</div>
            <div className="label">AI 면접 진행</div>
          </div>
          <div className="step">
            <div className="num">03</div>
            <div className="label">분석 리포트</div>
          </div>
        </div>
      </div>

      <div className="auth-right">
        <form className="auth-form" onSubmit={submit}>
          <div className="auth-tabs">
            <button
              type="button"
              className={tab === "login" ? "active" : ""}
              onClick={() => {
                setTab("login")
                setError("")
              }}
            >
              로그인
            </button>
            <button
              type="button"
              className={tab === "register" ? "active" : ""}
              onClick={() => {
                setTab("register")
                setError("")
              }}
            >
              회원가입
            </button>
          </div>

          {tab === "login" ? (
            <>
              <h2>다시 오신 걸 환영해요</h2>
              <p className="sub">저장한 문서로 바로 면접을 이어갈 수 있어요.</p>
            </>
          ) : (
            <>
              <h2>계정을 만들어 주세요</h2>
              <p className="sub">가입 후 바로 면접 연습을 시작할 수 있어요.</p>
            </>
          )}

          {tab === "register" && (
            <div className="field">
              <label>이름</label>
              <input
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="홍길동"
                required
              />
            </div>
          )}

          <div className="field">
            <label>이메일</label>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="seohyun@example.com"
              required
            />
          </div>

          <div className="field">
            <label>비밀번호</label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="••••••••"
              required
            />
          </div>

          {error && <div className="error-text">{error}</div>}

          <button type="submit" className="btn btn-dark btn-block" disabled={loading} style={{ marginTop: 8 }}>
            {loading ? "처리 중…" : tab === "login" ? "로그인" : "회원가입"}
          </button>

          <div className="auth-foot">
            <span style={{ color: "var(--ink-3)" }}>
              {tab === "login" ? "계정이 없으신가요?" : "이미 계정이 있으신가요?"}
            </span>
            <button type="button" onClick={() => setTab(tab === "login" ? "register" : "login")}>
              {tab === "login" ? "회원가입" : "로그인"}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
