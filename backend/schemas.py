from pydantic import BaseModel, EmailStr


# 회원가입 요청 형식
class UserCreate(BaseModel):
    email: EmailStr
    password: str
    name: str


# 로그인 요청 형식
class UserLogin(BaseModel):
    email: EmailStr
    password: str


# 회원 정보 응답 형식 (비밀번호는 절대 안 내보냄)
class UserOut(BaseModel):
    id: int
    email: str
    name: str

    class Config:
        from_attributes = True


# 로그인 성공 시 토큰 응답
class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


# 이력서 응답 형식
class ResumeOut(BaseModel):
    id: int
    title: str
    created_at: str | None = None

    class Config:
        from_attributes = True