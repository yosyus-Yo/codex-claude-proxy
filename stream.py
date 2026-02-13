"""ChatGPT Responses API 스트리밍 → Anthropic SSE 이벤트 변환"""
import json
import uuid
from typing import AsyncIterator


async def convert_stream(
    response_stream: AsyncIterator[bytes],
    model: str,
) -> AsyncIterator[str]:
    """Responses API SSE → Anthropic Messages SSE 변환"""

    msg_id = f"msg_{uuid.uuid4().hex[:24]}"
    block_idx = 0
    in_text_block = False
    input_tokens = 0
    output_tokens = 0

    # message_start 이벤트
    yield _sse("message_start", {
        "type": "message_start",
        "message": {
            "id": msg_id,
            "type": "message",
            "role": "assistant",
            "content": [],
            "model": model,
            "stop_reason": None,
            "stop_sequence": None,
            "usage": {"input_tokens": 0, "output_tokens": 0},
        },
    })

    async for line in _iter_sse_lines(response_stream):
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue

        etype = event.get("type", "")

        # 텍스트 출력 시작
        if etype == "response.output_text.delta":
            if not in_text_block:
                yield _sse("content_block_start", {
                    "type": "content_block_start",
                    "index": block_idx,
                    "content_block": {"type": "text", "text": ""},
                })
                in_text_block = True

            yield _sse("content_block_delta", {
                "type": "content_block_delta",
                "index": block_idx,
                "delta": {
                    "type": "text_delta",
                    "text": event.get("delta", ""),
                },
            })

        # 텍스트 블록 완료
        elif etype == "response.output_text.done":
            if in_text_block:
                yield _sse("content_block_stop", {
                    "type": "content_block_stop",
                    "index": block_idx,
                })
                block_idx += 1
                in_text_block = False

        # function_call 시작
        elif etype == "response.function_call_arguments.delta":
            call_id = event.get("call_id", "")
            # 새 function_call 블록이면 시작 이벤트
            if not hasattr(convert_stream, f"_fc_{call_id}"):
                setattr(convert_stream, f"_fc_{call_id}", True)
                if in_text_block:
                    yield _sse("content_block_stop", {
                        "type": "content_block_stop",
                        "index": block_idx,
                    })
                    block_idx += 1
                    in_text_block = False

                yield _sse("content_block_start", {
                    "type": "content_block_start",
                    "index": block_idx,
                    "content_block": {
                        "type": "tool_use",
                        "id": call_id,
                        "name": event.get("name", ""),
                        "input": {},
                    },
                })

            yield _sse("content_block_delta", {
                "type": "content_block_delta",
                "index": block_idx,
                "delta": {
                    "type": "input_json_delta",
                    "partial_json": event.get("delta", ""),
                },
            })

        # function_call 완료
        elif etype == "response.function_call_arguments.done":
            yield _sse("content_block_stop", {
                "type": "content_block_stop",
                "index": block_idx,
            })
            block_idx += 1

        # output item 완료
        elif etype == "response.output_item.done":
            item = event.get("item", {})
            item_type = item.get("type", "")

            if item_type == "function_call" and not in_text_block:
                # function_call item이 한번에 온 경우
                call_id = item.get("call_id", f"toolu_{uuid.uuid4().hex[:24]}")
                name = item.get("name", "")
                args = item.get("arguments", "{}")

                yield _sse("content_block_start", {
                    "type": "content_block_start",
                    "index": block_idx,
                    "content_block": {
                        "type": "tool_use",
                        "id": call_id,
                        "name": name,
                        "input": {},
                    },
                })
                yield _sse("content_block_delta", {
                    "type": "content_block_delta",
                    "index": block_idx,
                    "delta": {
                        "type": "input_json_delta",
                        "partial_json": args,
                    },
                })
                yield _sse("content_block_stop", {
                    "type": "content_block_stop",
                    "index": block_idx,
                })
                block_idx += 1

        # 응답 완료
        elif etype == "response.completed":
            resp = event.get("response", {})
            usage = resp.get("usage", {})
            input_tokens = usage.get("input_tokens", 0)
            output_tokens = usage.get("output_tokens", 0)

            # 열린 블록 닫기
            if in_text_block:
                yield _sse("content_block_stop", {
                    "type": "content_block_stop",
                    "index": block_idx,
                })

            output = resp.get("output", [])
            has_tool = any(i.get("type") == "function_call" for i in output)
            stop_reason = "tool_use" if has_tool else "end_turn"

            yield _sse("message_delta", {
                "type": "message_delta",
                "delta": {"stop_reason": stop_reason, "stop_sequence": None},
                "usage": {"output_tokens": output_tokens},
            })

    # message_stop
    yield _sse("message_stop", {"type": "message_stop"})


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


async def _iter_sse_lines(stream: AsyncIterator[bytes]) -> AsyncIterator[str]:
    """바이트 스트림에서 SSE data: 라인 추출 (UTF-8 안전)"""
    import codecs

    buffer = ""
    decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")

    async for chunk in stream:
        if isinstance(chunk, bytes):
            # Incremental decoder를 사용하여 불완전한 UTF-8 문자 처리
            text = decoder.decode(chunk, False)
        else:
            text = chunk

        buffer += text
        while "\n" in buffer:
            line, buffer = buffer.split("\n", 1)
            line = line.strip()
            if line.startswith("data: "):
                payload = line[6:]
                if payload != "[DONE]":
                    yield payload

    # 마지막 남은 바이트 처리
    final_text = decoder.decode(b"", True)
    if final_text:
        buffer += final_text
        if buffer.strip().startswith("data: "):
            payload = buffer.strip()[6:]
            if payload != "[DONE]":
                yield payload
