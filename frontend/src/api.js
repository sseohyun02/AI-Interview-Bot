// 백엔드 API 클라이언트
// 서버 주소는 환경변수(VITE_API_BASE)로 덮어쓸 수 있고, 없으면 로컬 기본값을 쓴다.
const BASE = import.meta.env.VITE_API_BASE || "http://localhost:8080"

// 로그인 토큰은 브라우저 localStorage 에 보관한다(새로고침해도 유지).
function getToken() {
  try {
    return localStorage.getItem("token")
  } catch {
    return null
  }
}

function setToken(t) {
  try {
    if (t) localStorage.setItem("token", t)
    else localStorage.removeItem("token")
  } catch {
    // 시크릿 모드 등에서 저장이 막혀도 앱은 계속 동작
  }
}

// 공통 요청 함수. 실패하면 서버가 준 detail 메시지를 담은 에러를 던진다.
async function request(path, { method = "GET", body, form, auth = true } = {}) {
  const headers = {}

  if (auth) {
    const t = getToken()
    if (t) headers["Authorization"] = `Bearer ${t}`
  }

  let payload
  if (form) {
    payload = form // FormData 는 Content-Type 을 브라우저가 자동 설정
  } else if (body !== undefined) {
    headers["Content-Type"] = "application/json"
    payload = JSON.stringify(body)
  }

  const res = await fetch(`${BASE}${path}`, { method, headers, body: payload })
  const text = await res.text()

  let data = null
  try {
    data = text ? JSON.parse(text) : null
  } catch {
    data = text
  }

  if (!res.ok) {
    const detail = data && data.detail ? data.detail : `요청 실패 (${res.status})`
    const err = new Error(detail)
    err.status = res.status
    throw err
  }
  return data
}

export const api = {
  register: (name, email, password) =>
    request("/api/auth/register", { method: "POST", auth: false, body: { name, email, password } }),
  login: (email, password) =>
    request("/api/auth/login", { method: "POST", auth: false, body: { email, password } }),
  me: () => request("/api/auth/me"),

  listResumes: () => request("/api/resumes"),
  uploadResume: (title, company, position, file) => {
    const fd = new FormData()
    fd.append("title", title)
    fd.append("company", company)
    fd.append("position", position)
    fd.append("file", file)
    return request("/api/resumes", { method: "POST", form: fd })
  },
  deleteResume: (id) => request(`/api/resumes/${id}`, { method: "DELETE" }),

  startInterview: (resumeId) =>
    request("/api/interview/start", { method: "POST", body: { resume_id: resumeId } }),
  submitAnswer: (sessionId, answer) =>
    request("/api/interview/answer", { method: "POST", body: { session_id: sessionId, answer } }),
  getReport: (sessionId) => request(`/api/interview/report/${sessionId}`),
}

export { getToken, setToken }
