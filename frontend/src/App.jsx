import { useEffect, useState } from "react"
import { api, getToken, setToken } from "./api"
import Auth from "./screens/Auth"
import Home from "./screens/Home"
import Prep from "./screens/Prep"
import Interview from "./screens/Interview"
import Analyzing from "./screens/Analyzing"
import Report from "./screens/Report"

// 상단 네비게이션 (면접/분석 화면에서는 숨김)
function TopNav({ user, onHome, onNew, onLogout }) {
  return (
    <div className="topnav">
      <div className="nav-left">
        <button
          onClick={onHome}
          style={{ background: "none", border: "none", padding: 0, display: "flex", alignItems: "center" }}
        >
          <span className="logo-mark" />
        </button>
        <div className="nav-links">
          <button onClick={onHome}>홈</button>
          <button onClick={onNew}>새 면접</button>
        </div>
      </div>
      <div className="nav-right">
        <span className="nav-user">{user.name}님</span>
        <button className="btn btn-sm" onClick={onLogout}>
          로그아웃
        </button>
      </div>
    </div>
  )
}

export default function App() {
  const [user, setUser] = useState(null)
  const [booting, setBooting] = useState(true)
  const [view, setView] = useState("home") // home | prep | interview | analyzing | report
  const [interview, setInterview] = useState(null)
  const [report, setReport] = useState(null)

  // 최초 진입: 저장된 토큰이 있으면 내 정보 조회해 자동 로그인
  useEffect(() => {
    const t = getToken()
    if (!t) {
      setBooting(false)
      return
    }
    api
      .me()
      .then(setUser)
      .catch(() => setToken(null))
      .finally(() => setBooting(false))
  }, [])

  function handleAuthed(u) {
    setUser(u)
    setView("home")
  }

  function logout() {
    setToken(null)
    setUser(null)
    setInterview(null)
    setReport(null)
    setView("home")
  }

  // 면접 시작 (홈/준비 화면 양쪽에서 호출). 실패 시 호출한 화면이 에러를 표시하도록 throw.
  async function beginInterview(resume) {
    const res = await api.startInterview(resume.id)
    setInterview({
      sessionId: res.session_id,
      resumeMeta: resume,
      messages: [{ role: "ai", text: res.question }],
      answeredCount: 0,
    })
    setReport(null)
    setView("interview")
  }

  if (booting) return <div className="boot">불러오는 중…</div>
  if (!user) return <Auth onAuthed={handleAuthed} />

  const showNav = view !== "interview"

  return (
    <div className="app">
      {showNav && (
        <TopNav user={user} onHome={() => setView("home")} onNew={() => setView("prep")} onLogout={logout} />
      )}

      {view === "home" && <Home user={user} onNew={() => setView("prep")} onStart={beginInterview} />}

      {view === "prep" && <Prep onStart={beginInterview} onHome={() => setView("home")} />}

      {view === "interview" && (
        <Interview
          state={interview}
          setState={setInterview}
          onEnd={(rep) => {
            setReport(rep)
            setView("analyzing")
          }}
          onExit={() => {
            setInterview(null)
            setView("home")
          }}
        />
      )}

      {view === "analyzing" && (
        <Analyzing count={report?.report_data?.total_questions} onDone={() => setView("report")} />
      )}

      {view === "report" && (
        <Report
          report={report}
          onHome={() => setView("home")}
          onRetry={async () => {
            try {
              await beginInterview(report.resumeMeta)
            } catch {
              setView("home")
            }
          }}
        />
      )}
    </div>
  )
}
