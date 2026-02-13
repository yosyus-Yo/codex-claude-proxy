"""OAuth 토큰 관리 - ~/.codex/auth.json 읽기 + 자동 갱신"""
import json
import os
import time
import base64
import httpx

AUTH_PATH = os.path.expanduser("~/.codex/auth.json")
# Codex CLI의 OAuth client_id
CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"
TOKEN_URL = "https://auth.openai.com/oauth/token"


class TokenManager:
    def __init__(self, auth_path: str = AUTH_PATH):
        self.auth_path = auth_path
        self._data = None
        self._load()

    def _load(self):
        with open(self.auth_path) as f:
            self._data = json.load(f)

    def _save(self):
        with open(self.auth_path, "w") as f:
            json.dump(self._data, f, indent=2)

    @property
    def tokens(self) -> dict:
        return self._data.get("tokens", {})

    @property
    def access_token(self) -> str | None:
        return self.tokens.get("access_token")

    @property
    def account_id(self) -> str | None:
        return self.tokens.get("account_id")

    @property
    def refresh_token(self) -> str | None:
        return self.tokens.get("refresh_token")

    def is_expired(self) -> bool:
        """JWT의 exp 클레임으로 만료 여부 확인"""
        token = self.access_token
        if not token:
            return True
        try:
            payload_b64 = token.split(".")[1]
            # base64 패딩 추가
            payload_b64 += "=" * (4 - len(payload_b64) % 4)
            payload = json.loads(base64.urlsafe_b64decode(payload_b64))
            # 만료 60초 전에 갱신
            return payload.get("exp", 0) < (time.time() + 60)
        except Exception:
            return True

    async def refresh_if_needed(self):
        """만료된 경우 토큰 갱신"""
        if not self.is_expired():
            return
        rt = self.refresh_token
        if not rt:
            raise RuntimeError("refresh_token 없음 - codex login 재실행 필요")

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                TOKEN_URL,
                json={
                    "grant_type": "refresh_token",
                    "refresh_token": rt,
                    "client_id": CLIENT_ID,
                },
            )
            if resp.status_code != 200:
                raise RuntimeError(f"토큰 갱신 실패: {resp.status_code} {resp.text}")
            data = resp.json()

        # 토큰 업데이트
        self._data["tokens"]["access_token"] = data["access_token"]
        if "refresh_token" in data:
            self._data["tokens"]["refresh_token"] = data["refresh_token"]
        self._data["last_refresh"] = time.strftime(
            "%Y-%m-%dT%H:%M:%S.000000Z", time.gmtime()
        )
        self._save()

    def get_headers(self) -> dict:
        """OpenAI API 호출용 인증 헤더"""
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }
        if self.account_id:
            headers["chatgpt-account-id"] = self.account_id
        return headers
