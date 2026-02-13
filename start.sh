#!/bin/bash
# Codex-Claude Proxy 실행 스크립트
# ChatGPT OAuth 토큰으로 Claude Code 환경에서 OpenAI 모델 사용

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PORT="${PROXY_PORT:-8082}"

# 의존성 확인
if ! command -v python3 &>/dev/null; then
  echo "❌ python3가 필요합니다"
  exit 1
fi

# auth.json 확인
if [ ! -f "$HOME/.codex/auth.json" ]; then
  echo "❌ ~/.codex/auth.json 없음"
  echo "   먼저 실행: codex login"
  exit 1
fi

# 의존성 설치 (최초 1회)
if [ ! -d "$SCRIPT_DIR/.venv" ]; then
  echo "📦 가상환경 생성 + 의존성 설치..."
  python3 -m venv "$SCRIPT_DIR/.venv"
  "$SCRIPT_DIR/.venv/bin/pip" install -q -r "$SCRIPT_DIR/requirements.txt"
fi

echo "🚀 Codex-Claude Proxy 시작 (port: $PORT)"
echo ""

# 모드 선택
case "${1:-proxy}" in
  proxy)
    # 프록시만 실행
    "$SCRIPT_DIR/.venv/bin/python" "$SCRIPT_DIR/server.py"
    ;;
  claude)
    # 프록시 + Claude Code 동시 실행
    "$SCRIPT_DIR/.venv/bin/python" "$SCRIPT_DIR/server.py" &
    PROXY_PID=$!
    sleep 2

    echo "🔗 Claude Code 시작 (OpenAI 백엔드)..."
    ANTHROPIC_AUTH_TOKEN="sk-proxy-codex" \
    ANTHROPIC_BASE_URL="http://localhost:$PORT" \
    claude

    echo "🛑 프록시 종료..."
    kill $PROXY_PID 2>/dev/null
    ;;
  *)
    echo "사용법: $0 [proxy|claude]"
    echo "  proxy  - 프록시 서버만 실행 (기본)"
    echo "  claude - 프록시 + Claude Code 동시 실행"
    ;;
esac
