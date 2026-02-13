"""Codex-Claude Proxy - Anthropic Messages API → ChatGPT Responses API (OAuth)"""
import os
import uuid
import httpx
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from auth import TokenManager
from converter import anthropic_to_responses, responses_to_anthropic
from stream import convert_stream
from models import map_model

# ChatGPT 백엔드 (OAuth 토큰 사용 가능, 구독 기반)
CHATGPT_API_URL = os.getenv(
    "CHATGPT_API_URL", "https://chatgpt.com/backend-api/codex/responses"
)
PORT = int(os.getenv("PROXY_PORT", "8082"))

app = FastAPI(title="Codex-Claude Proxy")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

token_mgr = TokenManager()


def _chatgpt_headers() -> dict:
    """ChatGPT 백엔드 전용 헤더"""
    headers = token_mgr.get_headers()
    headers.update({
        "Accept": "text/event-stream",
        "Accept-Language": "en-US,en;q=0.9",
        "Origin": "https://chatgpt.com",
        "Referer": "https://chatgpt.com/",
        "OpenAI-Beta": "responses=experimental",
        "originator": "codex_cli_rs",
        "session_id": str(uuid.uuid4()),
    })
    return headers


@app.get("/health")
async def health():
    return {"status": "ok", "token_expired": token_mgr.is_expired()}


@app.post("/v1/messages/count_tokens")
async def count_tokens(request: Request):
    """토큰 카운팅 (대략적인 추정)"""
    body = await request.json()

    # 간단한 토큰 추정: 1 token ≈ 4 characters
    total_chars = 0

    # system 메시지
    system = body.get("system", "")
    if isinstance(system, str):
        total_chars += len(system)
    elif isinstance(system, list):
        for block in system:
            if block.get("type") == "text":
                total_chars += len(block.get("text", ""))

    # messages
    for msg in body.get("messages", []):
        content = msg.get("content", "")
        if isinstance(content, str):
            total_chars += len(content)
        elif isinstance(content, list):
            for block in content:
                if block.get("type") == "text":
                    total_chars += len(block.get("text", ""))

    # 대략적인 토큰 수 추정
    input_tokens = total_chars // 4

    return {"input_tokens": input_tokens}


@app.post("/v1/messages")
async def messages(request: Request):
    """Anthropic Messages API → ChatGPT Responses API 프록시"""
    body = await request.json()
    is_stream = body.get("stream", False)
    original_model = body.get("model", "")

    # 토큰 갱신
    await token_mgr.refresh_if_needed()

    # Anthropic → Responses API 변환
    resp_body = anthropic_to_responses(body)
    mapped_model = resp_body["model"]

    print(f"[proxy] {original_model} → {mapped_model} | stream={is_stream}")

    # 요청에 tools가 있는지 확인
    if "tools" in resp_body:
        print(f"[proxy] 🔧 Tools available: {len(resp_body['tools'])} tools")

    # 마지막 메시지 확인
    if body.get("messages"):
        last_msg = body["messages"][-1]
        content = last_msg.get("content", "")
        if isinstance(content, str):
            preview = content[:100]
        else:
            preview = str(content)[:100]
        print(f"[proxy] 📝 Last message: {preview}...")

    headers = _chatgpt_headers()

    if is_stream:
        return StreamingResponse(
            _stream_proxy(resp_body, headers, mapped_model),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
            },
        )

    # non-streaming: Codex API는 stream=true 필수 → 내부적으로 스트리밍 후 조합
    anthropic_resp = await _collect_stream(resp_body, headers, mapped_model)
    return JSONResponse(content=anthropic_resp)


async def _collect_stream(resp_body: dict, headers: dict, model: str) -> dict:
    """non-streaming: 내부적으로 스트리밍 후 전체 응답 조합"""
    import json as _json

    resp_body["stream"] = True
    msg_id = f"msg_{uuid.uuid4().hex[:24]}"
    content_blocks: list[dict] = []
    current_text = ""
    current_tool: dict | None = None
    tool_args = ""
    input_tokens = 0
    output_tokens = 0
    stop_reason = "end_turn"

    async with httpx.AsyncClient(timeout=300) as client:
        async with client.stream(
            "POST", CHATGPT_API_URL, json=resp_body, headers=headers
        ) as resp:
            if resp.status_code != 200:
                error_body = await resp.aread()
                print(f"[proxy] collect error: {resp.status_code} {error_body[:200]}")
                return {
                    "error": {"type": "proxy_error", "message": error_body.decode()[:500]}
                }

            buffer = ""
            async for chunk in resp.aiter_bytes():
                text = chunk.decode("utf-8") if isinstance(chunk, bytes) else chunk
                buffer += text
                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    line = line.strip()
                    if not line.startswith("data: "):
                        continue
                    payload = line[6:]
                    if payload == "[DONE]":
                        continue
                    try:
                        event = _json.loads(payload)
                    except _json.JSONDecodeError:
                        continue

                    etype = event.get("type", "")

                    if etype == "response.output_text.delta":
                        current_text += event.get("delta", "")

                    elif etype == "response.output_text.done":
                        if current_text:
                            content_blocks.append({"type": "text", "text": current_text})
                            current_text = ""

                    elif etype == "response.function_call_arguments.delta":
                        if current_tool is None:
                            current_tool = {
                                "call_id": event.get("call_id", ""),
                                "name": event.get("name", ""),
                            }
                        tool_args += event.get("delta", "")

                    elif etype == "response.function_call_arguments.done":
                        if current_tool:
                            try:
                                args = _json.loads(tool_args)
                            except _json.JSONDecodeError:
                                args = {}
                            content_blocks.append({
                                "type": "tool_use",
                                "id": current_tool["call_id"] or f"toolu_{uuid.uuid4().hex[:24]}",
                                "name": current_tool["name"],
                                "input": args,
                            })
                            current_tool = None
                            tool_args = ""

                    elif etype == "response.output_item.done":
                        item = event.get("item", {})
                        if item.get("type") == "function_call":
                            call_id = item.get("call_id", f"toolu_{uuid.uuid4().hex[:24]}")
                            try:
                                args = _json.loads(item.get("arguments", "{}"))
                            except _json.JSONDecodeError:
                                args = {}
                            content_blocks.append({
                                "type": "tool_use",
                                "id": call_id,
                                "name": item.get("name", ""),
                                "input": args,
                            })

                    elif etype == "response.completed":
                        r = event.get("response", {})
                        usage = r.get("usage", {})
                        input_tokens = usage.get("input_tokens", 0)
                        output_tokens = usage.get("output_tokens", 0)
                        out = r.get("output", [])
                        has_tool = any(i.get("type") == "function_call" for i in out)
                        stop_reason = "tool_use" if has_tool else "end_turn"

                        # 응답 완료 로깅
                        print(f"[proxy] ✅ Response completed | stop_reason: {stop_reason} | "
                              f"has_tool: {has_tool} | tokens: {input_tokens}→{output_tokens}")

    # 아직 닫히지 않은 텍스트 블록
    if current_text:
        content_blocks.append({"type": "text", "text": current_text})

    return {
        "id": msg_id,
        "type": "message",
        "role": "assistant",
        "content": content_blocks,
        "model": model,
        "stop_reason": stop_reason,
        "stop_sequence": None,
        "usage": {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
        },
    }


async def _stream_proxy(resp_body: dict, headers: dict, model: str):
    """스트리밍 프록시"""
    resp_body["stream"] = True

    async with httpx.AsyncClient(timeout=300) as client:
        async with client.stream(
            "POST", CHATGPT_API_URL, json=resp_body, headers=headers
        ) as resp:
            if resp.status_code != 200:
                error_body = await resp.aread()
                print(f"[proxy] stream error: {resp.status_code} {error_body[:200]}")
                yield (
                    f'event: error\ndata: {{"type":"error","error":'
                    f'{{"type":"proxy_error","message":"HTTP {resp.status_code}"}}}}\n\n'
                )
                return

            async for chunk in convert_stream(resp.aiter_bytes(), model):
                yield chunk


if __name__ == "__main__":
    import uvicorn

    print(f"🚀 Codex-Claude Proxy on http://0.0.0.0:{PORT}")
    print(f"   Target: {CHATGPT_API_URL}")
    print(f"   Token expired: {token_mgr.is_expired()}")
    print()
    print("   사용법:")
    print(f'   ANTHROPIC_API_KEY="" ANTHROPIC_BASE_URL=http://localhost:{PORT} claude')
    uvicorn.run(app, host="0.0.0.0", port=PORT)
