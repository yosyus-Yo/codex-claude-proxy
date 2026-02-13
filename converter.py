"""Anthropic Messages API → ChatGPT Responses API 형식 변환"""
import json
import uuid
import os
from models import map_model

# 실제 모델 정보를 시스템 프롬프트에 표시할지 여부
REVEAL_ACTUAL_MODEL = os.getenv("REVEAL_ACTUAL_MODEL", "false").lower() == "true"


def anthropic_to_responses(body: dict) -> dict:
    """Anthropic Messages API 요청 → ChatGPT Responses API 요청 변환"""
    input_items = []

    # 실제 사용되는 모델
    actual_model = map_model(body.get("model", ""))

    # system → instructions
    instructions = ""
    system = body.get("system")
    if system:
        if isinstance(system, list):
            instructions = " ".join(
                b.get("text", "") for b in system if b.get("type") == "text"
            )
        else:
            instructions = system

    # 실제 모델 정보를 시스템 프롬프트에 추가
    if REVEAL_ACTUAL_MODEL:
        model_identity = (
            f"You are an AI assistant powered by OpenAI's {actual_model} model. "
            f"When asked about your model, identify yourself as {actual_model}, not Claude."
        )
        if instructions:
            instructions = f"{model_identity}\n\n{instructions}"
        else:
            instructions = model_identity

    # 메시지 변환
    for msg in body.get("messages", []):
        items = _convert_message(msg)
        input_items.extend(items)

    result = {
        "model": map_model(body.get("model", "")),
        "input": input_items,
        "stream": body.get("stream", False),
        "store": False,
    }

    # Codex API는 instructions 필수
    result["instructions"] = instructions or "You are a helpful assistant."

    # Codex API는 max_output_tokens, temperature 미지원 → 제외

    # tools 변환
    tools = body.get("tools")
    if tools:
        result["tools"] = [_convert_tool(t) for t in tools]
        # Codex CLI처럼 도구 사용을 강제하기 위해 "required" 시도
        result["tool_choice"] = "required"

        # 도구 변환 로깅
        tool_names = [t.get("name", "unknown") for t in tools]
        print(f"[converter] 🔧 Converting {len(tools)} tools: {', '.join(tool_names)}")
        print(f"[converter] 🔧 tool_choice set to: required")

    return result


def _convert_message(msg: dict) -> list[dict]:
    """단일 메시지 → Responses API input items"""
    role = msg.get("role")
    content = msg.get("content")
    # assistant → output_text, user → input_text
    text_type = "output_text" if role == "assistant" else "input_text"

    if isinstance(content, str):
        return [{
            "type": "message",
            "role": role,
            "content": [{"type": text_type, "text": content}],
        }]

    if not isinstance(content, list):
        return [{
            "type": "message",
            "role": role,
            "content": [{"type": text_type, "text": str(content)}],
        }]

    items = []
    content_parts = []

    for block in content:
        btype = block.get("type")

        if btype == "text":
            content_parts.append({"type": text_type, "text": block.get("text", "")})

        elif btype == "tool_use":
            # 어시스턴트의 tool_use → function_call item
            items.append({
                "type": "function_call",
                "id": block.get("id", f"call_{uuid.uuid4().hex[:24]}"),
                "call_id": block.get("id", f"call_{uuid.uuid4().hex[:24]}"),
                "name": block.get("name", ""),
                "arguments": json.dumps(block.get("input", {})),
            })

        elif btype == "tool_result":
            # tool_result → function_call_output item
            tool_content = block.get("content", "")
            if isinstance(tool_content, list):
                tool_content = " ".join(
                    b.get("text", "") for b in tool_content if b.get("type") == "text"
                )
            items.append({
                "type": "function_call_output",
                "call_id": block.get("tool_use_id", ""),
                "output": str(tool_content),
            })

        elif btype == "image":
            source = block.get("source", {})
            if source.get("type") == "base64":
                data_uri = (
                    f"data:{source.get('media_type', 'image/png')};"
                    f"base64,{source.get('data', '')}"
                )
                content_parts.append({
                    "type": "input_image",
                    "image_url": data_uri,
                })

        elif btype == "thinking":
            pass  # thinking 블록 무시

    # content_parts가 있으면 message item 추가
    if content_parts:
        items.insert(0, {
            "type": "message",
            "role": role,
            "content": content_parts,
        })

    return items


def _convert_tool(tool: dict) -> dict:
    """Anthropic tool → Responses API function tool"""
    converted = {
        "type": "function",
        "name": tool.get("name", ""),
        "description": tool.get("description", ""),
        "parameters": tool.get("input_schema", {"type": "object"}),
    }

    # 도구별 상세 로깅 (첫 3개만)
    name = converted["name"]
    if name:
        param_count = len(converted["parameters"].get("properties", {}))
        print(f"[converter]    • {name}: {param_count} parameters")

    return converted


def responses_to_anthropic(resp_data: dict, model: str) -> dict:
    """ChatGPT Responses API 응답 → Anthropic 응답 변환 (non-streaming)"""
    output = resp_data.get("output", [])
    content = []

    for item in output:
        item_type = item.get("type")
        if item_type == "message":
            for c in item.get("content", []):
                if c.get("type") == "output_text":
                    content.append({"type": "text", "text": c.get("text", "")})
        elif item_type == "function_call":
            try:
                args = json.loads(item.get("arguments", "{}"))
            except json.JSONDecodeError:
                args = {}
            content.append({
                "type": "tool_use",
                "id": item.get("call_id", f"toolu_{uuid.uuid4().hex[:24]}"),
                "name": item.get("name", ""),
                "input": args,
            })

    status = resp_data.get("status", "completed")
    stop_reason = "tool_use" if any(
        i.get("type") == "function_call" for i in output
    ) else "end_turn"

    usage = resp_data.get("usage", {})

    return {
        "id": resp_data.get("id", f"msg_{uuid.uuid4().hex[:24]}"),
        "type": "message",
        "role": "assistant",
        "content": content,
        "model": model,
        "stop_reason": stop_reason,
        "stop_sequence": None,
        "usage": {
            "input_tokens": usage.get("input_tokens", 0),
            "output_tokens": usage.get("output_tokens", 0),
        },
    }
