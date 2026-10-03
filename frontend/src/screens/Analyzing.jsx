import { useEffect, useState } from "react"

// 리포트 생성 전 잠깐 보여주는 분석 연출 화면.
// 실제 점수는 이미 받아왔고(onDone 뒤 리포트로 이동), 여기서는 단계 애니메이션만 보여준다.
const STEPS = [
  "답변 수집",
  "항목별 점수 산출 (구체성·일관성·적합성·논리성)",
  "강점·개선 필요 항목 분류",
  "리포트 생성",
]

export default function Analyzing({ count, onDone }) {
  const [active, setActive] = useState(0)

  useEffect(() => {
    // 단계별로 넘어가다가 마지막 단계 후 리포트로 이동
    const timers = []
    for (let i = 1; i < STEPS.length; i++) {
      timers.push(setTimeout(() => setActive(i), i * 650))
    }
    timers.push(setTimeout(onDone, STEPS.length * 650 + 400))
    return () => timers.forEach(clearTimeout)
  }, [onDone])

  return (
    <div className="analyzing">
      <div className="analyzing-inner">
        <h2>답변을 분석하고 있어요</h2>
        <p className="sub">잠시만 기다려주세요. 보통 10초 이내에 끝납니다.</p>

        <div className="card steps">
          {STEPS.map((label, i) => {
            const cls = i < active ? "done" : i === active ? "active" : ""
            const text = i === 0 && count ? `답변 ${count}개 수집` : label
            return (
              <div className={`step-item ${cls}`} key={i}>
                <span className="step-dot">{i < active ? "✓" : ""}</span>
                {text}
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}
