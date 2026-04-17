"""Streaming chat endpoint — Anthropic, Gemini, and Cerebras providers.

SSE event types:
  {"type":"text","text":"..."}                         partial assistant text
  {"type":"tool","name":...,"id":...,"input":{...}}    tool invocation
  {"type":"tool_result","name":...,"id":...,"ok":bool} tool finished
  {"type":"info","message":"..."}                      status (retry notice, etc.)
  {"type":"error","message":"..."}                     fatal error
  {"type":"done"}                                      end of turn
"""
from __future__ import annotations

import json
import re
import time
from typing import Any, Iterator

import anthropic
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

try:
    from google import genai as _google_genai
    from google.genai import types as _genai_types
    _GEMINI_AVAILABLE = True
except ImportError:
    _GEMINI_AVAILABLE = False

try:
    from cerebras.cloud.sdk import Cerebras as _CerebrasClient
    _CEREBRAS_AVAILABLE = True
except ImportError:
    _CEREBRAS_AVAILABLE = False

from .config import settings
from .tools import TOOLS, run_tool

router = APIRouter()

SYSTEM_PROMPT = """You are a data assistant for a loan database with 3 tables: applicants, employment, loans.

Use the available tools to answer questions. Call run_sql for analytical queries; call describe_table
first when you need to confirm column names. For ingestion, users drop CSV/Excel files into the
uploads folder and you can ingest them by filename with ingest_from_path.

Keep responses concise. When you run SQL, briefly show the query you ran and summarize the result."""

_GEMINI_UNSUPPORTED = {"minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum", "default"}

# Max retries for transient Gemini 429s (per-minute rate limit, not daily exhaustion)
_GEMINI_MAX_RETRIES = 2


def _clean_schema(obj: Any) -> Any:
    """Strip JSON Schema fields unsupported by Gemini's Schema proto."""
    if isinstance(obj, dict):
        return {k: _clean_schema(v) for k, v in obj.items() if k not in _GEMINI_UNSUPPORTED}
    if isinstance(obj, list):
        return [_clean_schema(i) for i in obj]
    return obj


class ChatMessage(BaseModel):
    role: str
    content: Any


class ChatRequest(BaseModel):
    messages: list[ChatMessage]
    provider: str = "anthropic"


def _sse(event: dict[str, Any]) -> str:
    return f"data: {json.dumps(event, default=str)}\n\n"


# ── Anthropic ──────────────────────────────────────────────────────────────────

def _stream_chat_anthropic(messages: list[dict[str, Any]]) -> Iterator[str]:
    if not settings.anthropic_api_key:
        yield _sse({"type": "error", "message": "ANTHROPIC_API_KEY is not set on the server."})
        yield _sse({"type": "done"})
        return

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    tools_with_cache = [dict(t) for t in TOOLS]
    if tools_with_cache:
        tools_with_cache[-1] = {**tools_with_cache[-1], "cache_control": {"type": "ephemeral"}}
    system = [{"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}]

    while True:
        try:
            with client.messages.stream(
                model=settings.anthropic_model,
                max_tokens=4096,
                system=system,
                tools=tools_with_cache,
                messages=messages,
            ) as stream:
                for event in stream:
                    if getattr(event, "type", None) == "content_block_delta":
                        delta = getattr(event, "delta", None)
                        if getattr(delta, "type", None) == "text_delta":
                            yield _sse({"type": "text", "text": delta.text})
                final = stream.get_final_message()
        except anthropic.APIError as exc:
            yield _sse({"type": "error", "message": f"Anthropic API error: {exc}"})
            yield _sse({"type": "done"})
            return

        messages.append({"role": "assistant", "content": [b.model_dump() for b in final.content]})

        if final.stop_reason != "tool_use":
            yield _sse({"type": "done"})
            return

        tool_results = []
        for block in final.content:
            if getattr(block, "type", None) != "tool_use":
                continue
            tool_input = block.input or {}
            yield _sse({"type": "tool", "name": block.name, "id": block.id, "input": tool_input})
            result = run_tool(block.name, tool_input)
            ok = "error" not in result
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": json.dumps(result, default=str),
                "is_error": not ok,
            })
            yield _sse({"type": "tool_result", "name": block.name, "id": block.id, "ok": ok})

        messages.append({"role": "user", "content": tool_results})


# ── Gemini ─────────────────────────────────────────────────────────────────────

def _build_gemini_tools() -> list:
    fds = [
        _genai_types.FunctionDeclaration(
            name=t["name"],
            description=t["description"],
            parameters=_clean_schema(t["input_schema"]),
        )
        for t in TOOLS
    ]
    return [_genai_types.Tool(function_declarations=fds)]


def _to_gemini_contents(messages: list[dict]) -> list[dict]:
    contents = []
    for m in messages:
        role = "model" if m["role"] == "assistant" else "user"
        content = m["content"]
        if isinstance(content, str):
            parts = [{"text": content}]
        elif isinstance(content, list):
            parts = [
                {"text": p["text"]}
                for p in content
                if isinstance(p, dict) and isinstance(p.get("text"), str) and p["text"]
            ] or [{"text": "(no text)"}]
        else:
            parts = [{"text": str(content)}]
        contents.append({"role": role, "parts": parts})
    return contents


def _gemini_retry_delay(exc: Exception) -> float:
    m = re.search(r"retryDelay.*?(\d+)s", str(exc))
    return float(m.group(1)) + 2.0 if m else 30.0


def _gemini_is_daily_quota(exc: Exception) -> bool:
    return "PerDay" in str(exc)


def _stream_chat_gemini(messages: list[dict[str, Any]]) -> Iterator[str]:
    if not _GEMINI_AVAILABLE:
        yield _sse({"type": "error", "message": "google-genai package not installed."})
        yield _sse({"type": "done"})
        return
    if not settings.gemini_api_key:
        yield _sse({"type": "error", "message": "GEMINI_API_KEY is not set on the server."})
        yield _sse({"type": "done"})
        return

    client = _google_genai.Client(api_key=settings.gemini_api_key)
    gemini_tools = _build_gemini_tools()
    config = _genai_types.GenerateContentConfig(
        system_instruction=SYSTEM_PROMPT,
        tools=gemini_tools,
        max_output_tokens=4096,
    )
    contents = _to_gemini_contents(messages)

    while True:
        function_calls: list = []

        # Retry loop for transient per-minute 429s
        for attempt in range(_GEMINI_MAX_RETRIES + 1):
            try:
                for chunk in client.models.generate_content_stream(
                    model=settings.gemini_model,
                    contents=contents,
                    config=config,
                ):
                    if chunk.text:
                        yield _sse({"type": "text", "text": chunk.text})
                    try:
                        for part in chunk.candidates[0].content.parts:
                            fc = getattr(part, "function_call", None)
                            if fc and getattr(fc, "name", None):
                                function_calls.append(fc)
                    except (AttributeError, IndexError):
                        pass
                break  # success — exit retry loop
            except Exception as exc:
                is_429 = "429" in str(exc) or "RESOURCE_EXHAUSTED" in str(exc)
                if is_429 and _gemini_is_daily_quota(exc):
                    yield _sse({
                        "type": "error",
                        "message": (
                            "Gemini daily free-tier quota exhausted. "
                            "Switch to Anthropic or Cerebras, or wait until midnight Pacific time."
                        ),
                    })
                    yield _sse({"type": "done"})
                    return
                if is_429 and attempt < _GEMINI_MAX_RETRIES:
                    delay = _gemini_retry_delay(exc)
                    yield _sse({"type": "info", "message": f"Gemini rate-limited — retrying in {delay:.0f}s…"})
                    time.sleep(delay)
                    function_calls = []
                    continue
                yield _sse({"type": "error", "message": f"Gemini API error: {exc}"})
                yield _sse({"type": "done"})
                return

        if not function_calls:
            yield _sse({"type": "done"})
            return

        contents.append({
            "role": "model",
            "parts": [
                {"function_call": {"name": fc.name, "args": dict(fc.args)}}
                for fc in function_calls
            ],
        })

        result_parts = []
        for fc in function_calls:
            args = dict(fc.args)
            yield _sse({"type": "tool", "name": fc.name, "id": fc.name, "input": args})
            result = run_tool(fc.name, args)
            ok = "error" not in result
            result_parts.append({
                "function_response": {
                    "name": fc.name,
                    "response": {"result": json.dumps(result, default=str)},
                }
            })
            yield _sse({"type": "tool_result", "name": fc.name, "id": fc.name, "ok": ok})

        contents.append({"role": "user", "parts": result_parts})


# ── Cerebras (OpenAI-compatible) ───────────────────────────────────────────────

def _build_cerebras_tools() -> list[dict]:
    return [
        {
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t["description"],
                "parameters": t["input_schema"],
            },
        }
        for t in TOOLS
    ]


def _to_openai_messages(messages: list[dict]) -> list[dict]:
    """Prepend system message and convert Anthropic-style history to OpenAI format."""
    result: list[dict] = [{"role": "system", "content": SYSTEM_PROMPT}]
    for m in messages:
        content = m.get("content", "")
        if isinstance(content, str):
            result.append({"role": m["role"], "content": content})
        elif isinstance(content, list):
            text = " ".join(
                p.get("text", "") for p in content
                if isinstance(p, dict) and isinstance(p.get("text"), str)
            )
            if text:
                result.append({"role": m["role"], "content": text})
    return result


def _stream_chat_cerebras(messages: list[dict[str, Any]]) -> Iterator[str]:
    if not _CEREBRAS_AVAILABLE:
        yield _sse({"type": "error", "message": "cerebras-cloud-sdk package not installed."})
        yield _sse({"type": "done"})
        return
    if not settings.cerebras_api_key:
        yield _sse({"type": "error", "message": "CEREBRAS_API_KEY is not set on the server."})
        yield _sse({"type": "done"})
        return

    client = _CerebrasClient(api_key=settings.cerebras_api_key)
    oai_tools = _build_cerebras_tools()
    oai_messages = _to_openai_messages(messages)

    while True:
        tool_calls_acc: dict[int, dict] = {}
        try:
            stream = client.chat.completions.create(
                model=settings.cerebras_model,
                messages=oai_messages,
                tools=oai_tools,
                stream=True,
                max_tokens=4096,
            )
            for chunk in stream:
                if not chunk.choices:
                    continue
                choice = chunk.choices[0]
                delta = choice.delta

                if getattr(delta, "content", None):
                    yield _sse({"type": "text", "text": delta.content})

                for tc in getattr(delta, "tool_calls", None) or []:
                    idx = tc.index
                    if idx not in tool_calls_acc:
                        tool_calls_acc[idx] = {
                            "id": getattr(tc, "id", None) or f"call_{idx}",
                            "name": "",
                            "arguments": "",
                        }
                    fn = getattr(tc, "function", None)
                    if fn:
                        tool_calls_acc[idx]["name"] += getattr(fn, "name", "") or ""
                        tool_calls_acc[idx]["arguments"] += getattr(fn, "arguments", "") or ""
        except Exception as exc:
            yield _sse({"type": "error", "message": f"Cerebras API error: {exc}"})
            yield _sse({"type": "done"})
            return

        if not tool_calls_acc:
            yield _sse({"type": "done"})
            return

        # Append assistant turn with tool calls
        oai_messages.append({
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": tc["id"],
                    "type": "function",
                    "function": {"name": tc["name"], "arguments": tc["arguments"]},
                }
                for tc in tool_calls_acc.values()
            ],
        })

        # Execute tools, append results
        for tc in tool_calls_acc.values():
            try:
                args = json.loads(tc["arguments"]) if tc["arguments"] else {}
            except json.JSONDecodeError:
                args = {}
            yield _sse({"type": "tool", "name": tc["name"], "id": tc["id"], "input": args})
            result = run_tool(tc["name"], args)
            ok = "error" not in result
            oai_messages.append({
                "role": "tool",
                "tool_call_id": tc["id"],
                "content": json.dumps(result, default=str),
            })
            yield _sse({"type": "tool_result", "name": tc["name"], "id": tc["id"], "ok": ok})


# ── Router ─────────────────────────────────────────────────────────────────────

_STREAMS = {
    "anthropic": _stream_chat_anthropic,
    "gemini":    _stream_chat_gemini,
    "cerebras":  _stream_chat_cerebras,
}


@router.post("/chat")
def chat(req: ChatRequest) -> StreamingResponse:
    history = [m.model_dump() for m in req.messages]
    stream_fn = _STREAMS.get(req.provider, _stream_chat_anthropic)
    return StreamingResponse(
        stream_fn(history),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
