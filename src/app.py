"""
🚀 CORE AGENT APPLICATION (DAY 03: CHATBOT VS REACT AGENT)
Thực thi so sánh giữa Chatbot Baseline (Cấp 2) và ReAct Agent kết nối MCP Server (Cấp 3).
"""

import json
import os
import sys
import time
from dotenv import load_dotenv

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

from mcp_server import MCPQAServer
from prompts import (
    CHATBOT_BASELINE_PROMPT,
    REACT_AGENT_SYSTEM_PROMPT,
    MAX_ITERATIONS
)
from providers import get_llm_provider

load_dotenv()

def load_test_cases():
    """Tải danh sách 5 test cases từ config/test_cases.json hoặc config/test_cases.example.json"""
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    config_path = os.path.join(base_dir, "config", "test_cases.json")
    if not os.path.exists(config_path):
        example_path = os.path.join(base_dir, "config", "test_cases.example.json")
        if os.path.exists(example_path):
            print("⚠️ [CONFIG NOTICE]: Chưa thấy file 'config/test_cases.json'. Đang dùng mẫu 'config/test_cases.example.json'.")
            print("👉 Hãy chạy: copy config/test_cases.example.json config/test_cases.json và viết test cases theo đề tài của bạn!\n")
            config_path = example_path
        else:
            config_path = "test_cases.json"
    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_waterfall_trace(trace_data: list):
    """Ghi vết log Waterfall Trace Log ra file docs/trace_waterfall.json"""
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    docs_dir = os.path.join(base_dir, "docs")
    os.makedirs(docs_dir, exist_ok=True)
    trace_path = os.path.join(docs_dir, "trace_waterfall.json")
    with open(trace_path, "w", encoding="utf-8") as f:
        json.dump(trace_data, f, ensure_ascii=False, indent=2)
    print(f"📊 [OBSERVABILITY]: Đã lưu {len(trace_data)} sự kiện Waterfall Trace tại '{trace_path}'!")


def run_baseline_chatbot(user_query: str, provider):
    """Chạy Chatbot gốc (Cấp 2) không có công cụ gọi Tool"""
    print(f"\n💬 [CHATBOT BASELINE] Câu hỏi: {user_query}")
    response = provider.generate(user_query, system_prompt=CHATBOT_BASELINE_PROMPT)
    print(f"🤖 Chatbot phản hồi:\n{response}")


def _observable_model_response(llm_response: dict) -> dict:
    """Chuẩn hóa đúng phần response mà provider/API thực sự công khai."""
    if llm_response.get("model_response"):
        return llm_response["model_response"]
    if llm_response.get("type") == "tool_call":
        return {
            "kind": "function_call",
            "tool_name": llm_response.get("tool_name"),
            "arguments": llm_response.get("arguments", {})
        }
    return {"kind": "text", "content": llm_response.get("content", "")}


def run_react_agent(user_query: str, provider, mcp_server: MCPQAServer) -> list:
    """
    [REACT AGENT LOOP] Thực thi vòng lặp Thought -> Action -> Observation với MCP Server.
    Hỗ trợ nhiều bước liên tiếp (multi-step chaining) bằng cách tích lũy một "scratchpad" văn bản
    chứa các bước Thought/Action/Observation trước đó và truyền lại cho LLM ở mỗi lượt gọi.
    Trả về danh sách trace log của phiên thực thi.
    """
    print(f"\n🤖 [REACT AGENT] Câu hỏi: {user_query}")

    step = 0
    trace_logs = []
    scratchpad = ""
    tools_list = mcp_server.list_tools()

    while step < MAX_ITERATIONS:
        step += 1
        step_start_time = time.time()
        print(f"\n--- 🔄 Vòng lặp ReAct Loop (Step {step}/{MAX_ITERATIONS}) ---")

        if scratchpad:
            prompt = (
                f"{user_query}\n\n--- Reasoning so far ---\n{scratchpad}"
                f"Dựa trên các bước trên, hãy quyết định bước tiếp theo (Action) hoặc đưa ra Final Answer."
            )
        else:
            prompt = user_query

        # Gọi LLM với Native Tool Calling Specs
        llm_response = provider.generate_with_tools(prompt, tools_list, system_prompt=REACT_AGENT_SYSTEM_PROMPT)
        llm_latency_ms = round((time.time() - step_start_time) * 1000, 2)

        thought = llm_response.get("thought", "Đang suy luận...")
        decision_summary = llm_response.get("decision_summary", thought)
        model_reasoning = llm_response.get("model_reasoning")
        reasoning_source = llm_response.get("reasoning_source", "not_provided")
        model_response = _observable_model_response(llm_response)
        fallback_used = bool(llm_response.get("fallback_used", False))
        print(f"🧠 [Thought]: {thought}")

        # Trường hợp 1: LLM quyết định trả lời bằng văn bản trực tiếp -> đây là Final Answer, dừng vòng lặp
        if llm_response.get("type") == "text":
            final_content = llm_response.get("content", "")
            print(f"🏁 [Final Answer]: {final_content}")
            trace_logs.append({
                "step": step,
                "query": user_query,
                "action_type": "FINAL_ANSWER",
                "thought": thought,
                "decision_summary": decision_summary,
                "model_reasoning": model_reasoning,
                "reasoning_source": reasoning_source,
                "model_response": model_response,
                "fallback_used": fallback_used,
                "output": final_content,
                "latency_ms": llm_latency_ms,
                "llm_latency_ms": llm_latency_ms,
                "tool_latency_ms": 0.0,
                "total_step_latency_ms": llm_latency_ms
            })
            break

        # Trường hợp 2: LLM đề xuất gọi Tool (Action) -> thực thi, ghi Observation, LẶP LẠI vòng lặp
        elif llm_response.get("type") == "tool_call":
            tool_name = llm_response.get("tool_name")
            arguments = llm_response.get("arguments", {})

            print(f"🛠️ [Action Proposed]: {tool_name}({arguments})")

            # Thực thi Tool qua MCP Server
            tool_start_time = time.time()
            mcp_result = mcp_server.call_tool(tool_name, arguments)
            tool_latency_ms = round((time.time() - tool_start_time) * 1000, 2)
            obs_data = mcp_result.get("result", {})
            obs_str = json.dumps(obs_data, ensure_ascii=False)
            print(f"👁️ [Observation từ MCP Server]: {obs_str}")

            trace_logs.append({
                "step": step,
                "query": user_query,
                "action_type": "TOOL_EXECUTION",
                "thought": thought,
                "decision_summary": decision_summary,
                "model_reasoning": model_reasoning,
                "reasoning_source": reasoning_source,
                "model_response": model_response,
                "fallback_used": fallback_used,
                "tool_name": tool_name,
                "arguments": arguments,
                "observation": obs_data,
                "latency_ms": llm_latency_ms,
                "llm_latency_ms": llm_latency_ms,
                "tool_latency_ms": tool_latency_ms,
                "total_step_latency_ms": round(llm_latency_ms + tool_latency_ms, 2)
            })

            # Nạp Thought/Action/Observation vào scratchpad để LLM quyết định bước tiếp theo
            args_str = json.dumps(arguments, ensure_ascii=False)
            scratchpad += f"Thought: {decision_summary}\nAction: {tool_name}({args_str})\nObservation: {obs_str}\n\n"
            # KHÔNG break ở đây — vòng lặp tiếp tục để LLM có thể quyết định gọi Tool tiếp theo
            # hoặc tổng hợp Final Answer dựa trên Observation vừa nhận được.
        else:
            break
    else:
        # Vòng lặp đã đạt MAX_ITERATIONS mà chưa có Final Answer -> chốt an toàn, không bịa dữ liệu
        last_obs = trace_logs[-1].get("observation") if trace_logs else None
        safety_text = (
            f"Đã đạt giới hạn {MAX_ITERATIONS} vòng lặp suy luận mà chưa tổng hợp được câu trả lời cuối cùng. "
            f"Quan sát gần nhất: {json.dumps(last_obs, ensure_ascii=False) if last_obs else 'không có'}."
        )
        print(f"⚠️ [MAX_ITERATIONS REACHED]: {safety_text}")
        trace_logs.append({
            "step": step + 1,
            "query": user_query,
            "action_type": "FINAL_ANSWER",
            "thought": "Đạt giới hạn MAX_ITERATIONS, dừng vòng lặp an toàn.",
            "decision_summary": "Dừng an toàn vì đã đạt giới hạn số vòng lặp.",
            "model_reasoning": None,
            "reasoning_source": "system_guardrail",
            "model_response": {"kind": "system_guardrail", "content": safety_text},
            "fallback_used": False,
            "output": safety_text,
            "latency_ms": 0.0,
            "llm_latency_ms": 0.0,
            "tool_latency_ms": 0.0,
            "total_step_latency_ms": 0.0
        })

    return trace_logs


if __name__ == "__main__":
    print("==========================================================")
    print("🧪 WEB QA TEST CASE LOOKUP & RETEST TICKET AGENT (DAY 03 LAB)")
    print("==========================================================")

    provider = get_llm_provider()
    mcp_server = MCPQAServer()
    
    print(f"🔌 LLM Provider: {provider.__class__.__name__}")
    print(f"🌐 MCP Server: {mcp_server.server_name}\n")
    
    tests = load_test_cases()
    print(f"✅ Đã tải thành công {len(tests)} Test Cases thử nghiệm.\n")
    
    if "--interactive" in sys.argv:
        print("🎮 [INTERACTIVE MODE] Trò chuyện trực tiếp với ReAct Agent:")
        print("💡 Gợi ý câu hỏi thử nghiệm:")
        print("   - Câu hỏi chung: 'What can this QA assistant help me with?'")
        print("   - Tra cứu test case: 'Look up test case TC-WEB-101 and summarize its status.'")
        print("   - Tạo phiếu retest: 'Check TC-MOB-202. If it is a confirmed high-severity failing test, retest is allowed, and no ticket exists, create a retest ticket requested by Nguyễn Văn An.'")
        print("   - Gõ 'exit' hoặc 'quit' để kết thúc phiên trò chuyện.\n")
        while True:
            try:
                user_input = input("👤 Bạn hỏi: ").strip()
                if not user_input or user_input.lower() in ["exit", "quit"]:
                    print("👋 Tạm biệt! Kết thúc phiên trò chuyện.")
                    break
                logs = run_react_agent(user_input, provider, mcp_server)
                save_waterfall_trace(logs)
            except (KeyboardInterrupt, EOFError):
                print("\n👋 Đã thoát phiên tương tác.")
                break
    elif "--all" in sys.argv:
        print(f"🚀 [TEST SUITE MODE] Kiểm tra {len(tests)} Test Cases:")
        completed_count = 0
        todo_count = 0
        all_traces = []
        
        for tc in tests:
            print(f"\n==================================================")
            print(f"🧪 [{tc['id']}] Loại test: {tc['type']} (Độ phức tạp: {tc['complexity']})")
            print(f"📌 Kỳ vọng: {tc['expected_behavior']}")
            
            if tc["question"].strip().startswith("TODO"):
                print(f"⏸️ [CHƯA KÍCH HOẠT - ĐANG LÀ TODO]:")
                print(f"   {tc['question']}")
                print(f"   👉 Hãy mở file 'config/test_cases.json' để viết câu hỏi thực tế cho Test Case này!")
                todo_count += 1
            else:
                logs = run_react_agent(tc["question"], provider, mcp_server)
                all_traces.extend(logs)
                completed_count += 1
                
        print(f"\n==================================================")
        print(f"📊 [KẾT QUẢ TEST SUITE]: Đã thực thi {completed_count}/{len(tests)} Test Cases | {todo_count} Test Cases đang chờ điền câu hỏi (TODO)")
        if all_traces:
            save_waterfall_trace(all_traces)
        print(f"💡 Để trò chuyện trực tiếp từng câu: Chạy 'python src/app.py --interactive'")
    else:
        # Chế độ mặc định khi chỉ gõ 'python src/app.py'
        print("ℹ️ HƯỚNG DẪN SỬ DỤNG CHƯƠNG TRÌNH:")
        print("  1. Chat trực tiếp liên tục:   python src/app.py --interactive")
        print("  2. Chạy toàn bộ Test Cases:    python src/app.py --all\n")
        
        sample_query = tests[1]["question"]
        print(f"--- 🏁 DEMO CHẠY THỬ 1 TEST CASE MẪU (TC02: Tra cứu test case) ---")
        logs = run_react_agent(sample_query, provider, mcp_server)
        save_waterfall_trace(logs)
        print("\n💡 Hãy thử ngay lệnh: python src/app.py --interactive để chat trực tiếp!")
