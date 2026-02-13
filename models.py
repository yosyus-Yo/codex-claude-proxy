"""모델 이름 매핑 - Anthropic 모델명 → ChatGPT Codex 모델"""
import os

# ChatGPT OAuth로 사용 가능한 Codex 모델:
# - gpt-5.3-codex        : 가장 강력한 코딩 모델
# - gpt-5.3-codex-spark  : 실시간 빠른 응답
# - gpt-5.2-codex        : 이전 버전
BIG_MODEL = os.getenv("CODEX_BIG_MODEL", "gpt-5.3-codex")
SMALL_MODEL = os.getenv("CODEX_SMALL_MODEL", "gpt-5.3-codex-spark")
THINKING_MODEL = os.getenv("CODEX_THINKING_MODEL", "gpt-5.3-codex")


def map_model(anthropic_model: str) -> str:
    """Anthropic 모델명을 Codex 모델로 변환"""
    name = anthropic_model.lower()
    if "opus" in name:
        return THINKING_MODEL
    if "sonnet" in name:
        return BIG_MODEL
    if "haiku" in name:
        return SMALL_MODEL
    # 이미 Codex/OpenAI 모델명이면 그대로
    if name.startswith(("gpt-", "o1", "o3", "o4")):
        return anthropic_model
    return BIG_MODEL
