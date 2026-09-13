"""
🔌 MULTI-PROVIDER LLM ADAPTER (Google Gemini, OpenAI & Offline Mock)
Hỗ trợ Native Tool Calling và chuyển đổi linh hoạt qua biến môi trường LLM_PROVIDER.
"""

import os
import sys
import json
import re
from typing import Dict, Any, List
from dotenv import load_dotenv

if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

load_dotenv()

class BaseLLMProvider:
    """Interface cơ sở cho các LLM Provider hỗ trợ Native Tool Calling"""
    def generate(self, prompt: str, system_prompt: str = "") -> str:
        raise NotImplementedError

    def generate_with_tools(self, prompt: str, tools_schema: List[Dict[str, Any]], system_prompt: str = "") -> Dict[str, Any]:
        raise NotImplementedError


_TEST_ID_RE = re.compile(r"TC-(?:WEB|MOB)-\d+", re.IGNORECASE)
_TICKET_ID_RE = re.compile(r"RTK-(?:WEB|MOB)-\d+", re.IGNORECASE)
_CREATE_INTENT_RE = re.compile(r"(create|tạo)\b[^\n]*\b(retest|ticket|phiếu)|retest ticket|phiếu retest", re.IGNORECASE)
_LIST_INTENT_RE = re.compile(r"\b(which|list|show|find|search|những|liệt kê|tìm|kiếm)\b", re.IGNORECASE)
_SEARCH_INTENT_RE = re.compile(r"\b(find|search|tìm|kiếm)\b|không nhớ", re.IGNORECASE)
_REQUESTED_BY_RE = re.compile(r"(?:requested by|yêu cầu bởi|bởi)\s+([^.,\n]+)", re.IGNORECASE)

_CREATE_OBS_RE = re.compile(r"Action: create_retest_ticket\([^\n]*\)\nObservation:\s*(\{.*?\})\n", re.DOTALL)
_CHECK_OBS_RE = re.compile(r"Action: check_retest_ticket_status\([^\n]*\)\nObservation:\s*(\{.*?\})\n", re.DOTALL)
_LIST_OBS_RE = re.compile(r"Action: list_test_cases\([^\n]*\)\nObservation:\s*(\{.*?\})\n", re.DOTALL)
_LOOKUP_OBS_RE = re.compile(r"Action: lookup_test_case\([^\n]*\)\nObservation:\s*(\{.*?\})\n", re.DOTALL)

_PRIORITY_MAP = {"critical": "Critical", "high": "High", "medium": "Medium", "low": "Low"}


def _fallback_result(prompt: str, tools_schema: List[Dict[str, Any]], system_prompt: str, requested_provider: str) -> Dict[str, Any]:
    result = MockOfflineProvider().generate_with_tools(prompt, tools_schema, system_prompt)
    result["fallback_used"] = True
    result["requested_provider"] = requested_provider
    return result


class MockOfflineProvider(BaseLLMProvider):
    """Offline Mock Provider dùng để chạy thử mà không tốn API Key.

    generate_with_tools mô phỏng một ReAct Agent xác định (deterministic) bằng cách đọc lại
    scratchpad "--- Reasoning so far ---" được app.py truyền vào (chứa các Thought/Action/Observation
    của các bước trước trong CÙNG một câu hỏi) để quyết định bước tiếp theo, thay vì chỉ nhìn câu hỏi gốc.
    """
    def __init__(self):
        self.model_name = "Offline-Mock-Model-2026"

    def generate(self, prompt: str, system_prompt: str = "") -> str:
        return f"[Mock Chatbot Response]: Xin chào! Tôi đã nhận được câu hỏi '{prompt}'. (Chế độ Chatbot không có Tool tra cứu dữ liệu thời gian thực)."

    def generate_with_tools(self, prompt: str, tools_schema: List[Dict[str, Any]], system_prompt: str = "") -> Dict[str, Any]:
        result = self._generate_step(prompt, tools_schema, system_prompt)
        decision_summary = result.get("thought", "Mock đã chọn bước tiếp theo.")
        result["decision_summary"] = decision_summary
        result["model_reasoning"] = decision_summary
        result["reasoning_source"] = "mock_deterministic"
        if result.get("type") == "tool_call":
            result["model_response"] = {
                "kind": "function_call",
                "tool_name": result.get("tool_name"),
                "arguments": result.get("arguments", {})
            }
        else:
            result["model_response"] = {
                "kind": "text",
                "content": result.get("content", "")
            }
        return result

    def _generate_step(self, prompt: str, tools_schema: List[Dict[str, Any]], system_prompt: str = "") -> Dict[str, Any]:
        # 1) Đã có kết quả create_retest_ticket trong scratchpad -> đây luôn là bước chốt cuối cùng
        create_match = _CREATE_OBS_RE.search(prompt)
        if create_match:
            obs = json.loads(create_match.group(1))
            if obs.get("status") == "SUCCESS":
                content = f"Đã tạo phiếu retest '{obs['ticket_id']}' cho test case {obs['test_id']} (priority: {obs['priority']})."
            else:
                content = f"Không thể tạo phiếu retest: {obs.get('message')}"
            return {"type": "text", "content": content,
                    "thought": "Đã nhận kết quả tạo ticket, tổng hợp câu trả lời cuối cùng."}

        # 2) Đã có kết quả check_retest_ticket_status -> chốt câu trả lời
        check_match = _CHECK_OBS_RE.search(prompt)
        if check_match:
            obs = json.loads(check_match.group(1))
            if obs.get("status") == "SUCCESS":
                content = f"Phiếu retest {obs['ticket_id']} (liên kết test case {obs['test_id']}) hiện đang ở trạng thái: {obs['ticket_status']}."
            else:
                content = obs.get("message", "Không tìm thấy phiếu retest được yêu cầu.")
            return {"type": "text", "content": content,
                    "thought": "Đã nhận kết quả tra cứu trạng thái phiếu, tổng hợp câu trả lời cuối cùng."}

        # 3) Đã có kết quả list_test_cases -> chốt câu trả lời
        list_match = _LIST_OBS_RE.search(prompt)
        if list_match:
            obs = json.loads(list_match.group(1))
            results = obs.get("results", [])
            if not results:
                content = "Không tìm thấy test case nào phù hợp với bộ lọc yêu cầu."
            else:
                items = "; ".join(
                    f"{r['test_id']} ({r.get('run_status')}, severity: {r.get('severity')})" for r in results
                )
                content = f"Tìm thấy {len(results)} test case phù hợp: {items}."
            return {"type": "text", "content": content,
                    "thought": "Đã nhận kết quả liệt kê test case, tổng hợp câu trả lời cuối cùng."}

        # 4) Đã có kết quả lookup_test_case -> quyết định bước tiếp theo (tạo ticket hoặc chốt câu trả lời)
        lookup_match = _LOOKUP_OBS_RE.search(prompt)
        if lookup_match:
            obs = json.loads(lookup_match.group(1))
            if obs.get("status") == "NOT_FOUND":
                return {"type": "text",
                        "content": f"Không tìm thấy test case '{obs.get('test_id')}' trong hệ thống. Vui lòng kiểm tra lại mã test case.",
                        "thought": "Test case không tồn tại -> từ chối, không tạo ticket."}

            create_intent = bool(_CREATE_INTENT_RE.search(prompt))
            if not create_intent:
                content = (
                    f"Test case {obs['test_id']} ({obs['platform']}): lỗi '{obs['failure_category']}', "
                    f"mức độ {obs['severity']}, trạng thái {obs['run_status']}. Chi tiết: {obs['failure_summary']}"
                )
                return {"type": "text", "content": content,
                        "thought": "Yêu cầu chỉ là tra cứu, không yêu cầu tạo ticket."}

            if not obs.get("retest_allowed"):
                return {"type": "text",
                        "content": f"Test case {obs['test_id']} hiện chưa đủ điều kiện retest (run_status='{obs['run_status']}').",
                        "thought": "retest_allowed=false -> từ chối tạo ticket."}

            if obs.get("existing_retest_ticket"):
                return {"type": "text",
                        "content": f"Test case {obs['test_id']} đã có phiếu retest '{obs['existing_retest_ticket']}' — không tạo phiếu trùng lặp.",
                        "thought": "Phát hiện existing_retest_ticket -> từ chối tạo trùng."}

            requested_by_match = _REQUESTED_BY_RE.search(prompt)
            if not requested_by_match:
                return {
                    "type": "text",
                    "content": "Test case đủ điều kiện retest. Vui lòng cung cấp tên người yêu cầu trước khi tạo phiếu.",
                    "thought": "Thiếu requested_by -> hỏi lại người dùng, không tạo ticket."
                }
            requested_by = requested_by_match.group(1).strip()
            reason = f"{obs['failure_category']} (severity: {obs['severity']}) - {obs['failure_summary']}"
            priority = _PRIORITY_MAP.get(str(obs.get("severity", "medium")).lower(), "Medium")
            return {
                "type": "tool_call",
                "tool_name": "create_retest_ticket",
                "arguments": {
                    "test_id": obs["test_id"], "requested_by": requested_by,
                    "reason": reason, "priority": priority
                },
                "thought": f"Test case {obs['test_id']} đủ điều kiện và chưa có ticket -> tạo phiếu retest mới."
            }

        # 5) Chưa có bước nào trước đó -> quyết định action đầu tiên dựa trên câu hỏi gốc
        ticket_ids = _TICKET_ID_RE.findall(prompt)
        if ticket_ids:
            return {"type": "tool_call", "tool_name": "check_retest_ticket_status",
                    "arguments": {"ticket_id": ticket_ids[0].upper()},
                    "thought": f"Người dùng hỏi về ticket {ticket_ids[0].upper()} -> tra cứu trạng thái phiếu."}

        test_ids = _TEST_ID_RE.findall(prompt)
        if test_ids:
            return {"type": "tool_call", "tool_name": "lookup_test_case",
                    "arguments": {"test_id": test_ids[0].upper()},
                    "thought": f"Người dùng đề cập test case {test_ids[0].upper()} -> tra cứu trước khi trả lời."}

        if _LIST_INTENT_RE.search(prompt):
            prompt_lower = prompt.lower()
            platform = "Mobile" if "mobile" in prompt_lower else ("Web" if "web" in prompt_lower else None)
            if "flaky" in prompt_lower:
                run_status = "flaky"
            elif "fail" in prompt_lower:
                run_status = "failed_confirmed"
            elif "pass" in prompt_lower:
                run_status = "passed"
            elif "investigation" in prompt_lower or "điều tra" in prompt_lower:
                run_status = "under_investigation"
            else:
                run_status = None
            severity = next((level for level in ("critical", "high", "medium", "low") if level in prompt_lower), None)
            original_query = prompt.split("\n\n--- Reasoning so far ---", 1)[0].strip()
            arguments = {
                k: v for k, v in {
                    "query": original_query if _SEARCH_INTENT_RE.search(prompt) else None,
                    "platform": platform,
                    "run_status": run_status,
                    "severity": severity
                }.items() if v
            }
            return {"type": "tool_call", "tool_name": "list_test_cases", "arguments": arguments,
                    "thought": "Câu hỏi mang tính liệt kê/tìm kiếm -> gọi list_test_cases với bộ lọc suy ra được."}

        return {
            "type": "text",
            "content": (
                "Tôi là Trợ lý QA. Tôi có thể tra cứu kết quả test case theo mã test_id, liệt kê test case theo "
                "bộ lọc, tạo phiếu retest khi đủ điều kiện, và tra cứu trạng thái phiếu retest theo mã ticket_id. "
                "Bạn cần hỗ trợ gì?"
            ),
            "thought": "Câu hỏi chung, không có mã test case/ticket cụ thể -> trả lời trực tiếp."
        }


class GeminiProvider(BaseLLMProvider):
    """Google Gemini Provider (Native Tool Calling với Google GenAI SDK)"""
    def __init__(self, api_key: str = None, model: str = None):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        self.model_name = model or os.getenv("LLM_MODEL") or "gemini-2.5-flash"

    def generate(self, prompt: str, system_prompt: str = "") -> str:
        if not self.api_key or self.api_key == "your_gemini_api_key_here":
            return "[Gemini Error]: Chưa cấu hình GEMINI_API_KEY trong file .env! Đang sử dụng chế độ Mock."
        try:
            from google import genai
            client = genai.Client(api_key=self.api_key)
            contents = f"{system_prompt}\n\n{prompt}" if system_prompt else prompt
            response = client.models.generate_content(model=self.model_name, contents=contents)
            return response.text
        except Exception as e:
            return f"[Gemini Exception]: {str(e)}"

    def generate_with_tools(self, prompt: str, tools_schema: List[Dict[str, Any]], system_prompt: str = "") -> Dict[str, Any]:
        if not self.api_key or self.api_key == "your_gemini_api_key_here":
            print("ℹ️ [Gemini Provider]: Chưa tìm thấy GEMINI_API_KEY hợp lệ. Tự động chuyển sang Mock Offline.")
            return _fallback_result(prompt, tools_schema, system_prompt, "gemini")
        
        try:
            from google import genai
            from google.genai import types

            client = genai.Client(api_key=self.api_key)
            
            # Chuẩn hóa function declarations cho Gemini SDK
            function_declarations = []
            for tool in tools_schema:
                # Bỏ qua các tool schema chưa được định nghĩa hoàn chỉnh
                if not tool.get("name") or not tool.get("parameters"):
                    continue
                function_declarations.append({
                    "name": tool["name"],
                    "description": tool.get("description", ""),
                    "parameters": tool.get("parameters", {})
                })

            config = types.GenerateContentConfig(
                system_instruction=system_prompt if system_prompt else None,
                tools=[{"function_declarations": function_declarations}] if function_declarations else None,
                temperature=0.2
            )

            response = client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config=config
            )

            public_parts = []
            candidates = getattr(response, "candidates", None) or []
            if candidates:
                content = getattr(candidates[0], "content", None)
                for part in getattr(content, "parts", None) or []:
                    # Không hiển thị phần được SDK đánh dấu là internal thought.
                    if getattr(part, "thought", False):
                        continue
                    part_text = getattr(part, "text", None)
                    if part_text:
                        public_parts.append(str(part_text).strip())
            public_reasoning = "\n".join(text for text in public_parts if text) or None

            # Kiểm tra xem Gemini có trả về Tool Call không
            if response.function_calls:
                call = response.function_calls[0]
                args = dict(call.args) if hasattr(call, 'args') and call.args else {}
                return {
                    "type": "tool_call",
                    "tool_name": call.name,
                    "arguments": args,
                    "thought": f"Gemini quyết định gọi công cụ '{call.name}' với tham số: {json.dumps(args, ensure_ascii=False)}",
                    "decision_summary": f"Gọi {call.name} để lấy dữ liệu cần cho bước tiếp theo.",
                    "model_reasoning": public_reasoning,
                    "reasoning_source": "provider_public_text" if public_reasoning else "not_provided",
                    "model_response": {
                        "kind": "function_call",
                        "public_text": public_reasoning,
                        "tool_name": call.name,
                        "arguments": args
                    }
                }
            else:
                final_text = response.text or ""
                return {
                    "type": "text",
                    "content": final_text,
                    "thought": "Gemini phản hồi trực tiếp bằng văn bản (không cần gọi công cụ).",
                    "decision_summary": "Kết thúc vòng lặp và trả lời người dùng.",
                    "model_reasoning": None,
                    "reasoning_source": "not_provided",
                    "model_response": {"kind": "text", "content": final_text}
                }

        except Exception as e:
            print(f"⚠️ [Gemini API Warning]: Không thể kết nối live API ({str(e)}). Tự động fallback về Mock.")
            return _fallback_result(prompt, tools_schema, system_prompt, "gemini")


class OpenAIProvider(BaseLLMProvider):
    """OpenAI Provider (Native Tool Calling với OpenAI SDK)"""
    def __init__(self, api_key: str = None, model: str = None):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.model_name = model or os.getenv("LLM_MODEL") or "gpt-4o-mini"

    def generate(self, prompt: str, system_prompt: str = "") -> str:
        if not self.api_key or self.api_key == "your_openai_api_key_here":
            return "[OpenAI Error]: Chưa cấu hình OPENAI_API_KEY trong file .env! Đang sử dụng chế độ Mock."
        try:
            from openai import OpenAI
            client = OpenAI(api_key=self.api_key)
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})
            response = client.chat.completions.create(model=self.model_name, messages=messages)
            return response.choices[0].message.content or ""
        except Exception as e:
            return f"[OpenAI Exception]: {str(e)}"

    def generate_with_tools(self, prompt: str, tools_schema: List[Dict[str, Any]], system_prompt: str = "") -> Dict[str, Any]:
        if not self.api_key or self.api_key == "your_openai_api_key_here":
            print("ℹ️ [OpenAI Provider]: Chưa tìm thấy OPENAI_API_KEY hợp lệ. Tự động chuyển sang Mock Offline.")
            return _fallback_result(prompt, tools_schema, system_prompt, "openai")

        try:
            from openai import OpenAI
            client = OpenAI(api_key=self.api_key)

            tools = []
            for tool in tools_schema:
                if not tool.get("name"):
                    continue
                tools.append({
                    "type": "function",
                    "function": {
                        "name": tool["name"],
                        "description": tool.get("description", ""),
                        "parameters": tool.get("parameters", {})
                    }
                })

            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})

            response = client.chat.completions.create(
                model=self.model_name,
                messages=messages,
                tools=tools if tools else None,
                tool_choice="auto" if tools else None
            )

            msg = response.choices[0].message
            if msg.tool_calls:
                call = msg.tool_calls[0]
                args = json.loads(call.function.arguments) if call.function.arguments else {}
                public_reasoning = msg.content.strip() if isinstance(msg.content, str) and msg.content.strip() else None
                return {
                    "type": "tool_call",
                    "tool_name": call.function.name,
                    "arguments": args,
                    "thought": f"OpenAI quyết định gọi công cụ '{call.function.name}' với tham số: {json.dumps(args, ensure_ascii=False)}",
                    "decision_summary": f"Gọi {call.function.name} để lấy dữ liệu cần cho bước tiếp theo.",
                    "model_reasoning": public_reasoning,
                    "reasoning_source": "provider_public_text" if public_reasoning else "not_provided",
                    "model_response": {
                        "kind": "function_call",
                        "public_text": public_reasoning,
                        "tool_name": call.function.name,
                        "arguments": args
                    }
                }
            else:
                final_text = msg.content or ""
                return {
                    "type": "text",
                    "content": final_text,
                    "thought": "OpenAI phản hồi trực tiếp bằng văn bản (không cần gọi công cụ).",
                    "decision_summary": "Kết thúc vòng lặp và trả lời người dùng.",
                    "model_reasoning": None,
                    "reasoning_source": "not_provided",
                    "model_response": {"kind": "text", "content": final_text}
                }
        except Exception as e:
            print(f"⚠️ [OpenAI API Warning]: Không thể kết nối live API ({str(e)}). Tự động fallback về Mock.")
            return _fallback_result(prompt, tools_schema, system_prompt, "openai")


def get_llm_provider() -> BaseLLMProvider:
    """Factory function khởi tạo Provider theo LLM_PROVIDER env variable"""
    provider_type = os.getenv("LLM_PROVIDER", "gemini").lower()
    
    if provider_type == "gemini":
        key = os.getenv("GEMINI_API_KEY")
        if key and key != "your_gemini_api_key_here":
            return GeminiProvider()
        else:
            return MockOfflineProvider()
    elif provider_type == "openai":
        key = os.getenv("OPENAI_API_KEY")
        if key and key != "your_openai_api_key_here":
            return OpenAIProvider()
        else:
            return MockOfflineProvider()
    elif provider_type == "mock":
        return MockOfflineProvider()
    else:
        return MockOfflineProvider()
