# Codex-Claude Proxy

[한글 문서 (Korean)](README.ko.md)

Use OpenAI Codex models in Claude Code using your ChatGPT Plus/Pro subscription OAuth token.

This proxy translates Anthropic's Messages API format into ChatGPT's Responses API format, allowing Claude Code to communicate with OpenAI's Codex backend using your existing ChatGPT subscription — no separate API credits needed.

## How It Works

```
Claude Code  ──(Anthropic Messages API)──>  Proxy (localhost:8082)
                                               │
                                               ▼
                                        Format Translation
                                     (Messages → Responses API)
                                               │
                                               ▼
ChatGPT Backend  <──(Responses API + OAuth)──  Proxy
(chatgpt.com/backend-api/codex/responses)
```

**Model Mapping:**

| Claude Code requests | Proxy sends |
|---------------------|-------------|
| claude-opus-* | gpt-5.3-codex |
| claude-sonnet-* | gpt-5.3-codex |
| claude-haiku-* | gpt-5.3-codex |

> All models default to `gpt-5.3-codex`. You can change this — see [Custom Model Mapping](#custom-model-mapping).

## Prerequisites

- **Python 3.11+**
- **ChatGPT Plus or Pro subscription**
- **OpenAI Codex CLI** (for OAuth login)
- **Claude Code** installed

## Setup

### 1. Install OpenAI Codex CLI and Login

```bash
# Install Codex CLI
npm install -g @openai/codex

# Login with your ChatGPT account
codex login
```

This creates `~/.codex/auth.json` with your OAuth tokens.

### 2. Clone and Install

```bash
git clone https://github.com/yosyus-Yo/codex-claude-proxy.git
cd codex-claude-proxy

# Create virtual environment and install dependencies
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

### 3. Logout from Claude Code (one-time)

```bash
claude /logout
```

This is required so Claude Code uses the proxy instead of its native Anthropic authentication.

### 4. Start the Proxy

**Option A: Quick Setup with zsh alias (Recommended)**

1. **Copy the zsh config:**

```bash
cp .zshrc-codex-proxy ~/.zshrc-codex-proxy
echo 'source ~/.zshrc-codex-proxy' >> ~/.zshrc
source ~/.zshrc
```

2. **Usage:**

```bash
ccy       # Auto-start proxy + launch Claude Code with Codex models
cpstop    # Stop proxy if needed
```

The `ccy` command automatically starts the proxy if it's not running, or uses the existing one if it's already running.

**Option B: Manual execution (recommended for seeing logs)**

Terminal 1 — Start proxy:
```bash
cd codex-claude-proxy
.venv/bin/python server.py
```

Terminal 2 — Start Claude Code:
```bash
ANTHROPIC_AUTH_TOKEN="sk-proxy" ANTHROPIC_BASE_URL=http://localhost:8082 claude
```

**Option C: All-in-one with start.sh**

```bash
./start.sh claude
```

This starts the proxy in the background and launches Claude Code automatically.

### 5. Verify

In the proxy terminal, you should see logs like:
```
[proxy] claude-sonnet-4-5-20250929 → gpt-5.3-codex | stream=True
INFO:     127.0.0.1:62670 - "POST /v1/messages?beta=true HTTP/1.1" 200 OK
```

## Switching Back to Anthropic

To return to using Anthropic's native API:

```bash
claude /login
```

Then start Claude Code normally without environment variables.

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `PROXY_PORT` | `8082` | Proxy server port |
| `CHATGPT_API_URL` | `https://chatgpt.com/backend-api/codex/responses` | ChatGPT backend URL |
| `CODEX_BIG_MODEL` | `gpt-5.3-codex` | Model for Opus/Sonnet requests |
| `CODEX_SMALL_MODEL` | `gpt-5.3-codex-spark` | Model for Haiku requests |
| `CODEX_THINKING_MODEL` | `gpt-5.3-codex` | Model for thinking/reasoning |

### Custom Model Mapping

All models default to `gpt-5.3-codex`. Override via environment variables or by editing `models.py` directly:

```bash
# Use different models per role
CODEX_BIG_MODEL=gpt-5.2-codex \
CODEX_SMALL_MODEL=gpt-5.3-codex-spark \
CODEX_THINKING_MODEL=gpt-5.3-codex \
.venv/bin/python server.py
```

Or edit `models.py`:

```python
BIG_MODEL = os.getenv("CODEX_BIG_MODEL", "gpt-5.3-codex")       # sonnet → this
SMALL_MODEL = os.getenv("CODEX_SMALL_MODEL", "gpt-5.3-codex")   # haiku → this
THINKING_MODEL = os.getenv("CODEX_THINKING_MODEL", "gpt-5.3-codex")  # opus → this
```

**Available Codex models:**

| Model | Description |
|-------|-------------|
| `gpt-5.3-codex` | Most capable coding model |
| `gpt-5.3-codex-spark` | Faster, lighter responses |
| `gpt-5.2-codex` | Previous version |

## Project Structure

```
codex-claude-proxy/
├── server.py          # FastAPI proxy server
├── auth.py            # OAuth token management (read/refresh ~/.codex/auth.json)
├── converter.py       # Anthropic Messages API ↔ ChatGPT Responses API conversion
├── stream.py          # SSE streaming event translation
├── models.py          # Model name mapping (Anthropic → Codex)
├── start.sh           # One-click launcher script
└── requirements.txt   # Python dependencies
```

## API Translation Details

### Request Translation (Anthropic → Responses API)

| Anthropic | Responses API |
|-----------|---------------|
| `system` | `instructions` |
| `messages[].content` (user) | `input[].content[].type: "input_text"` |
| `messages[].content` (assistant) | `input[].content[].type: "output_text"` |
| `tool_use` blocks | `function_call` items |
| `tool_result` blocks | `function_call_output` items |
| `max_tokens` | *(removed — Codex API doesn't support it)* |
| `temperature` | *(removed — Codex API doesn't support it)* |

### Response Translation (Responses API → Anthropic)

| Responses API | Anthropic |
|---------------|-----------|
| `response.output_text.delta` | `content_block_delta` (text_delta) |
| `response.function_call_arguments.delta` | `content_block_delta` (input_json_delta) |
| `response.completed` | `message_delta` + `message_stop` |

## Troubleshooting

### "SessionStart:startup hook error"

This is from Claude Code's plugin hooks, not the proxy. The proxy is working correctly. You can safely ignore this error.

### "model not supported when using Codex with a ChatGPT account"

Only Codex-specific models work with ChatGPT OAuth. Make sure `models.py` uses `gpt-5.3-codex` or `gpt-5.3-codex-spark`. Standard models like `gpt-4o` or `o4-mini` are not supported.

### "Instructions are required"

The Codex API requires the `instructions` field. The proxy automatically adds a default instruction if none is provided via the system message.

### "Stream must be set to true"

The Codex API only supports streaming. The proxy handles this internally — even non-streaming requests are collected via streaming.

### Token expired

The proxy auto-refreshes expired OAuth tokens using the refresh token in `~/.codex/auth.json`. If refresh fails, re-run `codex login`.

### Claude Code shows "Opus 4.6" or "Sonnet 4.5" model name

This is Claude Code's UI displaying its configured model name. The actual model being used is the Codex model shown in proxy logs (e.g., `gpt-5.3-codex`).

## License

MIT
