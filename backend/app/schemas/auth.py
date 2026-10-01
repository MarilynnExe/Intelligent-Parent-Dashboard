from pydantic import BaseModel


class LoginRequest(BaseModel):
    email_or_username: str
    password: str


class UserInfo(BaseModel):
    user_id: int
    full_name: str
    email_or_username: str
    role: str
    phone_number: str | None = None


class LoginResponse(BaseModel):
    access_token: str
    token_type: str
    user: UserInfo