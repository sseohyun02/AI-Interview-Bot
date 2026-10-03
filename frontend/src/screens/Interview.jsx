import { useEffect, useRef, useState } from "react"
import { api } from "../api"

// 면접 채팅 화면
export default function Interview({ state, setState, onEnd, onExit }) {
  const [answer, setAnswer] = useState("")
  const [sending, setSending] = useState(false)
  const [error, setError] = useState("")
  const bodyRef = useRef(null)

  const { sessionId, resumeMeta, messages, answeredCount } = state

  // 새 메시지가 쌓이면 맨 아래로 스크롤
  useEffect(() => {
    const el = bodyRef.current
    if (el) el.scrollTop = el.scrollHeight
  }, [messages, sending])

  async function submit() {
    const text = answer.trim()
    if (!text || sending) return

    // 내 답변을 먼저 화면에 반영
    setState((s) => ({ ...s, messages: [...s.messages, { role: "me", text }] }))
    setAnswer("")
    setSending(true)
    setError("")

    try {
      const res = await api.submitAnswer(sessionId, text)

      if (res.ended) {
        // 면접 종료 → 리포트 데이터를 들고 분석 화면으로
        onEnd({
          report_data: res.report_data,
          final_report: res.final_report,
          resumeMeta,
        })
        return
      }

      setState((s) => ({
        ...s,
        messages: [...s.messages, { role: "ai", text: res.question }],
        answeredCount: res.answered_count ?? s.answeredCount + 1,
      }))
    } catch (err) {
      // 실패 시 방금 보낸 답변을 입력창에 되돌려 재시도 가능하게
      setError(err.message)
      setAnswer(text)
      setState((s) => ({ ...s, messages: s.messages.slice(0, -1) }))
    } finally {
      setSending(false)
    }
  }

  function onKeyDown(e) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault()
      submit()
    }
  }

  function endInterview() {
    if (confirm("면접을 종료하고 나갈까요? 지금 나가면 이 면접은 저장되지 않습니다.")) {
      onExit()
    }
  }

  // 총 질문 수는 백엔드가 정해주지 않으므로(동적 종료) 비율 대신 답변 수만 표시.
  // 바는 진행 '느낌'만 주도록 답변 수에 따라 완만히 차오른다.
  const barWidth = Math.min(90, 12 + answeredCount * 11) + "%"

  return (
    <div className="iv">
      <div className="iv-head">
        <span className="logo-mark" style={{ width: 24, height: 24 }} />
        <span className="title">모의면접 진행 중</span>

        <div className="iv-progress">
          <div className="iv-bar">
            <span style={{ width: barWidth }} />
          </div>
          <span className="iv-count">답변 {answeredCount}개</span>
        </div>

        <button className="btn btn-sm" style={{ marginLeft: 16 }} onClick={endInterview}>
          면접 종료
        </button>
      </div>

      <div className="iv-body" ref={bodyRef}>
        <div className="iv-thread">
          {messages.map((m, i) => (
            <div className={`msg ${m.role}`} key={i}>
              <div className="who">
                {m.role === "ai" ? (
                  <>
                    <span className="avatar">AI</span> AI 면접관
                  </>
                ) : (
                  "내 답변"
                )}
              </div>
              <div className="bubble">{m.text}</div>
            </div>
          ))}

          {sending && (
            <div className="msg ai">
              <div className="who">
                <span className="avatar">AI</span> AI 면접관
              </div>
              <div className="bubble">
                <span className="typing">
                  <i />
                  <i />
                  <i />
                </span>
              </div>
            </div>
          )}
        </div>
      </div>

      <div className="iv-foot">
        <div className="iv-inputwrap">
          {error && <div className="error-text" style={{ marginBottom: 8 }}>{error}</div>}
          <textarea
            className="iv-input"
            value={answer}
            onChange={(e) => setAnswer(e.target.value)}
            onKeyDown={onKeyDown}
            placeholder="답변을 입력하세요. 구체적인 상황과 수치를 함께 말하면 좋아요."
            disabled={sending}
          />
          <div className="iv-inputbar">
            <span className="meta">{answer.length}자 · Enter로 제출 (Shift+Enter 줄바꿈)</span>
            <button className="btn btn-primary" onClick={submit} disabled={sending || !answer.trim()}>
              {sending ? "처리 중…" : "답변 제출"}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
