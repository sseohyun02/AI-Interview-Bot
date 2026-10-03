// 면접 분석 리포트 화면 (백엔드 report_data 기반)
function barClass(v) {
  if (v >= 0.75) return "bar-fill"
  if (v < 0.5) return "bar-fill low"
  return "bar-fill mid"
}

function todayStr() {
  const d = new Date()
  return `${d.getFullYear()}년 ${d.getMonth() + 1}월 ${d.getDate()}일`
}

export default function Report({ report, onHome, onRetry }) {
  const rd = report?.report_data
  const resumeMeta = report?.resumeMeta

  // 구조화 데이터가 없으면(예외적 경우) 텍스트 보고서라도 보여준다.
  if (!rd) {
    return (
      <div className="page page-narrow">
        <div className="report-head">
          <div>
            <div className="eyebrow">{todayStr()}</div>
            <h1>면접 분석 리포트</h1>
          </div>
          <div className="report-actions">
            <button className="btn" onClick={onHome}>홈으로</button>
          </div>
        </div>
        <div className="card" style={{ padding: 24, whiteSpace: "pre-wrap", fontSize: 14, lineHeight: 1.7 }}>
          {report?.final_report || "리포트를 생성할 수 있는 평가 데이터가 부족합니다."}
        </div>
      </div>
    )
  }

  const docLabel = resumeMeta
    ? `${resumeMeta.title}${resumeMeta.company ? ` · ${resumeMeta.company} ${resumeMeta.position || ""}` : ""}`
    : ""

  return (
    <div className="page page-narrow">
      <div className="report-head">
        <div>
          <div className="eyebrow">
            {todayStr()}
            {docLabel ? ` · ${docLabel}` : ""}
          </div>
          <h1>면접 분석 리포트</h1>
        </div>
        <div className="report-actions">
          <button className="btn" onClick={onHome}>
            홈으로
          </button>
          <button className="btn btn-primary" onClick={onRetry}>
            같은 문서로 다시 면접
          </button>
        </div>
      </div>

      <div className="report-top">
        <div className="score-card">
          <div className="k">종합 점수</div>
          <div className="big">
            {rd.overall_score}
            <span> / 10</span>
          </div>
          <div className="formula">4개 항목 평균 {rd.overall_avg} × 10</div>
          <div className="divider">
            <span className="label">평가에 사용된 질문</span>
            <span className="v">{rd.total_questions}개</span>
          </div>
        </div>

        <div className="card bars-card">
          <div className="bars-head">
            <h3>항목별 평균 점수</h3>
            <div className="legend">
              <span>
                <i className="g" />강점 0.75 이상
              </span>
              <span>
                <i className="o" />개선 필요 0.5 미만
              </span>
            </div>
          </div>

          {rd.criteria.map((c) => (
            <div className="bar-row" key={c.name}>
              <div className="name">{c.name}</div>
              <div className="bar-track">
                <div className={barClass(c.avg)} style={{ width: `${Math.round(c.avg * 100)}%` }} />
              </div>
              <div className="val">{c.avg.toFixed(2)}</div>
            </div>
          ))}

          <div className="bar-axis">
            <div />
            <div className="ticks">
              <span style={{ left: "0%" }}>0</span>
              <span style={{ left: "50%" }}>0.5</span>
              <span style={{ left: "75%" }}>0.75</span>
              <span style={{ left: "100%" }}>1</span>
            </div>
            <div />
          </div>
        </div>
      </div>

      <div className="report-cols">
        <div className="card rc">
          <h3>
            <span className="dot g" />강점<span className="note">평균 0.75 이상</span>
          </h3>
          {rd.strengths.length === 0 && <div className="rc-empty">아직 뚜렷한 강점 항목이 없어요.</div>}
          {rd.strengths.map((s) => (
            <div className="rc-item good" key={s.name}>
              <div className="top">
                <span className="nm">{s.name}</span>
                <span className="sc">{s.avg.toFixed(2)}</span>
              </div>
              <div className="cmt">{s.comment}</div>
            </div>
          ))}
        </div>

        <div className="card rc">
          <h3>
            <span className="dot o" />개선 필요<span className="note">평균 0.5 미만</span>
          </h3>
          {rd.improvements.length === 0 && (
            <div className="rc-empty">0.5 미만으로 떨어진 항목은 없어요. 잘하셨어요!</div>
          )}
          {rd.improvements.map((s) => (
            <div className="rc-item bad" key={s.name}>
              <div className="top">
                <span className="nm">{s.name}</span>
                <span className="sc">{s.avg.toFixed(2)}</span>
              </div>
              <div className="cmt">{s.comment}</div>
            </div>
          ))}
        </div>
      </div>

      {rd.feedback && (
        <div className="card feedback-card">
          <h3>종합 평가</h3>
          <p>{rd.feedback}</p>
        </div>
      )}
    </div>
  )
}
