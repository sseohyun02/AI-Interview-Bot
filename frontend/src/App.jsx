import { useState } from "react"

const API_BASE = "http://localhost:8080"

function App() {
  const [sessionId, setSessionId] = useState(null)
  const [file, setFile] = useState(null)
  const [loading, setLoading] = useState(false)

  // 대화 내역: { role: "면접관" | "지원자", text: "..." } 객체들의 배열
  const [messages, setMessages] = useState([])
  // 답변 입력칸의 현재 값
  const [answer, setAnswer] = useState("")
  // 면접 종료 여부
  const [ended, setEnded] = useState(false)
  // 최종 리포트
  const [report, setReport] = useState("")

  // 면접 시작
  async function startInterview() {
    if (!file) {
      alert("이력서 파일을 선택해주세요.")
      return
    }
    setLoading(true)
    try {
      const formData = new FormData()
      formData.append("file", file)

      const res = await fetch(`${API_BASE}/api/interview/start`, {
        method: "POST",
        body: formData,
      })
      const data = await res.json()

      setSessionId(data.session_id)
      // 첫 질문을 대화 목록에 추가
      setMessages([{ role: "면접관", text: data.question }])
    } catch (err) {
      alert("면접 시작 중 오류가 발생했습니다.")
      console.error(err)
    } finally {
      setLoading(false)
    }
  }

  // 답변 제출
  async function submitAnswer() {
    if (!answer.trim()) return
    setLoading(true)

    // 내가 쓴 답변을 먼저 대화 목록에 추가
    const myAnswer = answer
    setMessages((prev) => [...prev, { role: "지원자", text: myAnswer }])
    setAnswer("")  // 입력칸 비우기

    try {
      const res = await fetch(`${API_BASE}/api/interview/answer`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: sessionId, answer: myAnswer }),
      })
      const data = await res.json()

      if (data.ended) {
        // 면접 종료 → 최종 리포트 표시
        setEnded(true)
        setReport(data.final_report)
      } else {
        // 다음 질문을 대화 목록에 추가
        setMessages((prev) => [...prev, { role: "면접관", text: data.question }])
      }
    } catch (err) {
      alert("답변 제출 중 오류가 발생했습니다.")
      console.error(err)
    } finally {
      setLoading(false)
    }
  }

  // === 화면 1: 업로드 화면 ===
  if (!sessionId) {
    return (
      <div style={{ maxWidth: 600, margin: "50px auto", padding: 20 }}>
        <h1>AI 면접관</h1>
        <p>이력서를 업로드하면 면접이 시작됩니다.</p>
        <input
          type="file"
          accept=".pdf,.docx"
          onChange={(e) => setFile(e.target.files[0])}
        />
        <br /><br />
        <button onClick={startInterview} disabled={loading}>
          {loading ? "준비 중..." : "면접 시작"}
        </button>
      </div>
    )
  }

  // === 화면 3: 리포트 화면 ===
  if (ended) {
    return (
      <div style={{ maxWidth: 600, margin: "50px auto", padding: 20 }}>
        <h1>면접 결과</h1>
        <div style={{ whiteSpace: "pre-wrap", lineHeight: 1.6 }}>{report}</div>
      </div>
    )
  }

  // === 화면 2: 채팅 화면 ===
  return (
    <div style={{ maxWidth: 600, margin: "50px auto", padding: 20 }}>
      <h1>면접 진행 중</h1>

      {/* 대화 목록 */}
      <div style={{ border: "1px solid #ddd", borderRadius: 8, padding: 16, minHeight: 300, marginBottom: 16 }}>
        {messages.map((msg, i) => (
          <div key={i} style={{ marginBottom: 12, textAlign: msg.role === "지원자" ? "right" : "left" }}>
            <div style={{ fontSize: 12, color: "#888" }}>{msg.role}</div>
            <div style={{
              display: "inline-block",
              padding: "8px 12px",
              borderRadius: 12,
              background: msg.role === "지원자" ? "#dbeafe" : "#f3f4f6",
            }}>
              {msg.text}
            </div>
          </div>
        ))}
      </div>

      {/* 답변 입력 */}
      <div style={{ display: "flex", gap: 8 }}>
        <input
          type="text"
          value={answer}
          onChange={(e) => setAnswer(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") submitAnswer() }}
          placeholder="답변을 입력하세요"
          disabled={loading}
          style={{ flex: 1, padding: 8 }}
        />
        <button onClick={submitAnswer} disabled={loading}>
          {loading ? "처리 중..." : "전송"}
        </button>
      </div>
    </div>
  )
}

export default App