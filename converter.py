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

    # system 메시지 구성
    system_content = ""
    system = body.get("system")
    if system:
        if isinstance(system, list):
            system_content = " ".join(
                b.get("text", "") for b in system if b.get("type") == "text"
            )
        else:
            system_content = system

    # 도구가 있을 때 도구 사용 지시를 맨 앞에 추가 (가장 먼저 보도록)
    if body.get("tools"):
        tool_instructions = (
            "=== MANDATORY TOOL USAGE PROTOCOL - FOLLOW EXACTLY ===\n"
            "\n"
            "ABSOLUTE RULE: When ANY task requires action, you MUST call tools IMMEDIATELY.\n"
            "- If asked to read → call Read tool FIRST, then respond\n"
            "- If asked to search → call Grep/Glob tool FIRST, then respond\n"
            "- If asked to run → call Bash tool FIRST, then respond\n"
            "- If asked to edit → call Edit tool FIRST, then respond\n"
            "- If asked to create → call Write tool FIRST, then respond\n"
            "\n"
            "FORBIDDEN BEHAVIOR:\n"
            "❌ \"I will read the file\" WITHOUT calling Read\n"
            "❌ \"Let me check\" WITHOUT calling Grep\n"
            "❌ \"I can help you\" WITHOUT calling tools\n"
            "❌ Explaining what you would do WITHOUT doing it\n"
            "\n"
            "REQUIRED BEHAVIOR:\n"
            "✅ User: \"read config.json\" → You: [CALL Read tool immediately]\n"
            "✅ User: \"find all .ts files\" → You: [CALL Glob tool immediately]\n"
            "✅ User: \"check git status\" → You: [CALL Bash tool immediately]\n"
            "\n"
            "This is NOT optional. This is NOT a suggestion. This is MANDATORY.\n"
            "Failure to call tools when needed = task failure.\n"
            "\n"
            "=== END MANDATORY PROTOCOL ===\n\n"
        )
        system_content = tool_instructions + (system_content or "")

    # 실제 모델 정보를 시스템 프롬프트에 추가 (도구 지시 다음에)
    if REVEAL_ACTUAL_MODEL:
        model_identity = (
            f"You are an AI assistant powered by OpenAI's {actual_model} model. "
            f"When asked about your model, identify yourself as {actual_model}, not Claude.\n\n"
        )
        system_content = model_identity + system_content if system_content else model_identity

    # 메시지 변환 (system은 input에 넣지 않고 instructions로 사용)
    for msg in body.get("messages", []):
        items = _convert_message(msg)
        input_items.extend(items)

    result = {
        "model": map_model(body.get("model", "")),
        "input": input_items,
        "stream": body.get("stream", False),
        "store": False,
    }

    # Codex API는 instructions 필수 (일반 Responses API와 다름)
    result["instructions"] = system_content or "You are a helpful assistant."

    # tools 변환
    tools = body.get("tools")
    if tools:
        result["tools"] = [_convert_tool(t) for t in tools]
        result["tool_choice"] = "auto"

        # 도구 변환 로깅
        tool_names = [t.get("name", "unknown") for t in tools]
        print(f"[converter] 🔧 Converting {len(tools)} tools: {', '.join(tool_names)}")
        print(f"[converter] 🔧 tool_choice set to: auto")
        print(f"[converter] 🔧 instructions required by Codex API (not in input)")

    # 전체 요청 body 로깅 (디버깅용)
    print("\n[converter] 📋 FULL REQUEST BODY:")
    print(f"[converter]   model: {result['model']}")
    print(f"[converter]   stream: {result['stream']}")
    print(f"[converter]   instructions length: {len(result.get('instructions', ''))} chars")
    if result.get("instructions"):
        # instructions 앞뒤 200자만 표시
        inst = result["instructions"]
        if len(inst) > 400:
            print(f"[converter]   instructions preview: {inst[:200]}...{inst[-200:]}")
        else:
            print(f"[converter]   instructions: {inst}")
    print(f"[converter]   input items: {len(result['input'])} items")

    # 실제 user message 찾기 및 출력
    actual_user_message = None
    for i, item in enumerate(result['input']):
        item_type = item.get('type', 'unknown')
        print(f"[converter]     [{i}] type: {item_type}, role: {item.get('role', 'N/A')}")
        if item_type == "message":
            content = item.get('content', [])
            for c in content:
                c_type = c.get('type', 'unknown')
                if c_type in ['input_text', 'output_text']:
                    text = c.get('text', '')
                    preview = text[:100] if len(text) > 100 else text
                    print(f"[converter]         {c_type}: {preview}...")
                    # system-reminder가 아닌 실제 메시지 찾기
                    if c_type == 'input_text' and not text.startswith('<system-reminder>') and not text.startswith('<command-'):
                        if actual_user_message is None or len(text) > len(actual_user_message):
                            actual_user_message = text

    if actual_user_message:
        print(f"\n[converter] 💬 ACTUAL USER MESSAGE:")
        print(f"[converter]   {actual_user_message[:300]}")
        print()

    if result.get("tools"):
        print(f"[converter]   tools: {len(result['tools'])} tools defined")
        print(f"[converter]   tool_choice: {result.get('tool_choice', 'N/A')}")
    print("[converter] 📋 END REQUEST BODY\n")

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
            # call_id가 비어있으면 자동 생성
            call_id = block.get("tool_use_id", "") or f"call_{uuid.uuid4().hex[:24]}"
            items.append({
                "type": "function_call_output",
                "id": call_id,  # id 필드 추가 (Responses API 요구사항)
                "call_id": call_id,
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
