# Codex-Claude Proxy

ChatGPT Plus/Pro 구독의 OAuth 토큰을 사용하여 Claude Code에서 OpenAI Codex 모델을 사용할 수 있게 해주는 프록시입니다.

Anthropic의 Messages API 형식을 ChatGPT의 Responses API 형식으로 변환하여, 기존 ChatGPT 구독으로 Claude Code와 통신할 수 있습니다 — 별도의 API 크레딧이 필요 없습니다.

## 동작 원리

```
Claude Code  ──(Anthropic Messages API)──>  Proxy (localhost:8082)
                                               │
                                               ▼
                                        형식 변환
                                  (Messages → Responses API)
                                               │
                                               ▼
ChatGPT 백엔드  <──(Responses API + OAuth)──  Proxy
(chatgpt.com/backend-api/codex/responses)
```

**모델 매핑:**

| Claude Code 요청 | 프록시가 전송하는 모델 |
|------------------|---------------------|
| claude-opus-* | gpt-5.3-codex |
| claude-sonnet-* | gpt-5.3-codex |
| claude-haiku-* | gpt-5.3-codex |

> 모든 모델은 기본적으로 `gpt-5.3-codex`를 사용합니다. 변경 방법은 [모델 커스터마이징](#모델-커스터마이징)을 참조하세요.

## 필요 사항

- **Python 3.11+**
- **ChatGPT Plus 또는 Pro 구독**
- **OpenAI Codex CLI** (OAuth 로그인용)
- **Claude Code** 설치

## 설치 방법

### 1. OpenAI Codex CLI 설치 및 로그인

```bash
# Codex CLI 설치
npm install -g @openai/codex

# ChatGPT 계정으로 로그인
codex login
```

이 과정에서 `~/.codex/auth.json`에 OAuth 토큰이 생성됩니다.

### 2. 프록시 클론 및 설치

```bash
git clone https://github.com/yosyus-Yo/codex-claude-proxy.git
cd codex-claude-proxy

# 가상환경 생성 및 의존성 설치
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

### 3. Claude Code에서 로그아웃 (최초 1회)

```bash
claude /logout
```

프록시를 사용하기 위해 기존 Anthropic 인증을 제거합니다.

### 4. 프록시 시작 및 사용

**옵션 A: 간편 설정 (zsh alias 사용 - 추천)**

1. **zsh 설정 적용:**

```bash
cp .zshrc-codex-proxy ~/.zshrc-codex-proxy
echo 'source ~/.zshrc-codex-proxy' >> ~/.zshrc
source ~/.zshrc
```

2. **사용:**

```bash
ccy      # 프록시 자동 시작 + Codex 모델 Claude Code 실행 (gpt-5.3-codex로 응답)
cpstop   # 프록시 종료
```

**동작 방식:**
- `ccy` 명령어는 프록시를 `REVEAL_ACTUAL_MODEL=true`로 자동 시작합니다
- 모델이 자신을 "gpt-5.3-codex"로 소개합니다 (실제 정체성 공개)
- 프록시가 이미 실행 중이면 재시작합니다

**옵션 B: 수동 실행 (로그 확인용 추천)**

터미널 1 — 프록시 실행:
```bash
cd codex-claude-proxy
.venv/bin/python server.py
```

터미널 2 — Claude Code 실행:
```bash
ANTHROPIC_AUTH_TOKEN="sk-proxy-codex" ANTHROPIC_BASE_URL=http://localhost:8082 claude
```

**옵션 C: start.sh 사용 (올인원)**

```bash
./start.sh claude
```

프록시를 백그라운드로 실행하고 Claude Code를 자동으로 엽니다.

### 5. 검증

프록시 터미널에서 다음과 같은 로그가 보여야 합니다:
```
[proxy] claude-sonnet-4-5-20250929 → gpt-5.3-codex | stream=True
INFO:     127.0.0.1:62670 - "POST /v1/messages?beta=true HTTP/1.1" 200 OK
```

## Anthropic API로 돌아가기

Anthropic의 네이티브 API를 다시 사용하려면:

```bash
claude /login
```

그리고 환경변수 없이 Claude Code를 실행하세요.

## 설정

### 환경변수

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `PROXY_PORT` | `8082` | 프록시 서버 포트 |
| `CHATGPT_API_URL` | `https://chatgpt.com/backend-api/codex/responses` | ChatGPT 백엔드 URL |
| `CODEX_BIG_MODEL` | `gpt-5.3-codex` | Opus/Sonnet 요청용 모델 |
| `CODEX_SMALL_MODEL` | `gpt-5.3-codex` | Haiku 요청용 모델 |
| `CODEX_THINKING_MODEL` | `gpt-5.3-codex` | 사고/추론용 모델 |
| `REVEAL_ACTUAL_MODEL` | `true` (ccy 기본값) | `true`일 때 모델이 실제 정체성(gpt-5.3-codex)을 공개 |

### 모델 커스터마이징

모든 모델은 기본적으로 `gpt-5.3-codex`를 사용합니다. 환경변수 또는 `models.py` 직접 수정으로 변경 가능합니다:

```bash
# 역할별로 다른 모델 사용
CODEX_BIG_MODEL=gpt-5.2-codex \
CODEX_SMALL_MODEL=gpt-5.3-codex-spark \
CODEX_THINKING_MODEL=gpt-5.3-codex \
.venv/bin/python server.py
```

또는 `models.py` 수정:

```python
BIG_MODEL = os.getenv("CODEX_BIG_MODEL", "gpt-5.3-codex")       # sonnet → 여기
SMALL_MODEL = os.getenv("CODEX_SMALL_MODEL", "gpt-5.3-codex")   # haiku → 여기
THINKING_MODEL = os.getenv("CODEX_THINKING_MODEL", "gpt-5.3-codex")  # opus → 여기
```

**사용 가능한 Codex 모델:**

| 모델 | 설명 |
|------|------|
| `gpt-5.3-codex` | 가장 강력한 코딩 모델 |
| `gpt-5.3-codex-spark` | 빠르고 가벼운 응답 |
| `gpt-5.2-codex` | 이전 버전 |

## 프로젝트 구조

```
codex-claude-proxy/
├── server.py          # FastAPI 프록시 서버
├── auth.py            # OAuth 토큰 관리 (~/.codex/auth.json 읽기/갱신)
├── converter.py       # Anthropic Messages API ↔ ChatGPT Responses API 변환
├── stream.py          # SSE 스트리밍 이벤트 변환
├── models.py          # 모델 이름 매핑 (Anthropic → Codex)
├── start.sh           # 원클릭 실행 스크립트
├── .zshrc-codex-proxy # zsh alias 설정 파일
└── requirements.txt   # Python 의존성
```

## API 변환 상세

### 요청 변환 (Anthropic → Responses API)

| Anthropic | Responses API |
|-----------|---------------|
| `system` | `instructions` |
| `messages[].content` (user) | `input[].content[].type: "input_text"` |
| `messages[].content` (assistant) | `input[].content[].type: "output_text"` |
| `tool_use` 블록 | `function_call` 항목 |
| `tool_result` 블록 | `function_call_output` 항목 |
| `max_tokens` | *(제거됨 — Codex API 미지원)* |
| `temperature` | *(제거됨 — Codex API 미지원)* |

### 응답 변환 (Responses API → Anthropic)

| Responses API | Anthropic |
|---------------|-----------|
| `response.output_text.delta` | `content_block_delta` (text_delta) |
| `response.function_call_arguments.delta` | `content_block_delta` (input_json_delta) |
| `response.completed` | `message_delta` + `message_stop` |

## 문제 해결

### "SessionStart:startup hook error"

Claude Code의 플러그인 hook 오류이며, 프록시와는 무관합니다. 프록시는 정상 작동 중입니다. 이 오류는 무시해도 됩니다.

### "model not supported when using Codex with a ChatGPT account"

ChatGPT OAuth로는 Codex 전용 모델만 작동합니다. `models.py`가 `gpt-5.3-codex` 또는 `gpt-5.3-codex-spark`를 사용하는지 확인하세요. `gpt-4o`나 `o4-mini` 같은 일반 모델은 지원되지 않습니다.

### "Instructions are required"

Codex API는 `instructions` 필드가 필수입니다. 프록시가 system 메시지가 없으면 자동으로 기본 instruction을 추가합니다.

### "Stream must be set to true"

Codex API는 스트리밍만 지원합니다. 프록시가 내부적으로 처리합니다 — non-streaming 요청도 스트리밍으로 수집됩니다.

### 토큰 만료

프록시는 `~/.codex/auth.json`의 refresh token을 사용하여 만료된 OAuth 토큰을 자동 갱신합니다. 갱신 실패 시 `codex login`을 다시 실행하세요.

### Claude Code에서 "Opus 4.6" 또는 "Sonnet 4.5" 모델명 표시

Claude Code의 UI가 설정된 모델명을 표시하는 것입니다. 실제로 사용되는 모델은 프록시 로그에 표시되는 Codex 모델입니다 (예: `gpt-5.3-codex`).

### 프록시를 계속 켜두어도 되나요?

네, 프록시는 stateless 서버이므로 메모리도 적게 사용하고 계속 켜두셔도 됩니다. `ccy` 명령어를 사용하면 자동으로 관리되므로 신경쓸 필요가 없습니다.

## 라이선스

MIT
