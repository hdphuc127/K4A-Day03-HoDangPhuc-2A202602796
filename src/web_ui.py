"""
🖥️ WEB QA REACT EXPLORER (prototype, không thay thế CLI chấm điểm chính của Lab)
Giao diện demo kết hợp Test Case Explorer, chat và Agent Map quanh ReAct Agent hiện có.
Chạy: python src/web_ui.py, sau đó mở trình duyệt tại http://127.0.0.1:5000
"""

import os
import sys
import time
from datetime import datetime, timezone
from uuid import uuid4

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

from flask import Flask, request, jsonify, send_from_directory

from app import run_react_agent, load_test_cases
from mcp_server import MCPQAServer
from providers import get_llm_provider
from tools import reset_mock_data, search_test_case_records, TEST_CASE_DATABASE, RETEST_TICKETS

STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")

flask_app = Flask(__name__, static_folder=STATIC_DIR, static_url_path="")

provider = get_llm_provider()
mcp_server = MCPQAServer()


def _provider_metadata():
    requested = os.getenv("LLM_PROVIDER", "gemini").lower()
    actual = provider.__class__.__name__.replace("Provider", "").replace("Offline", "").lower()
    if isinstance(actual, str) and actual.startswith("mock"):
        actual = "mock"
    return {
        "requested_provider": requested,
        "provider": actual,
        "provider_class": provider.__class__.__name__,
        "model": getattr(provider, "model_name", "unknown"),
        "execution_mode": "mock" if actual == "mock" else "live",
        "configured_fallback": requested != actual
    }


def _optional_bool(value):
    if value is None or value == "":
        return None
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


@flask_app.route("/")
def index():
    return send_from_directory(STATIC_DIR, "index.html")


@flask_app.route("/api/test_cases")
def api_test_cases():
    """Giữ tương thích: đây là các kịch bản demo/evaluation, không phải domain test cases."""
    return jsonify(load_test_cases())


@flask_app.route("/api/scenarios")
def api_scenarios():
    return jsonify(load_test_cases())


@flask_app.route("/api/meta")
def api_meta():
    return jsonify(_provider_metadata())


@flask_app.route("/api/qa/test-cases")
def api_qa_test_cases():
    results = search_test_case_records(
        query=request.args.get("q"),
        platform=request.args.get("platform"),
        run_status=request.args.get("run_status"),
        severity=request.args.get("severity"),
        retest_allowed=_optional_bool(request.args.get("retest_allowed")),
        has_ticket=_optional_bool(request.args.get("has_ticket")),
        limit=request.args.get("limit", 20)
    )
    return jsonify({"count": len(results), "results": results})


@flask_app.route("/api/database")
def api_database():
    return jsonify({
        "test_cases": TEST_CASE_DATABASE,
        "tickets": RETEST_TICKETS
    })


@flask_app.route("/api/chat", methods=["POST"])
def api_chat():
    body = request.get_json(silent=True) or {}
    query = (body.get("query") or "").strip()
    if not query:
        return jsonify({"error": "query là bắt buộc"}), 400

    context = body.get("context") or {}
    selected_test_id = str(context.get("test_id") or "").strip().upper()
    agent_query = query
    if selected_test_id and selected_test_id not in query.upper():
        agent_query = f"{query}\n\nTest case đang được người dùng chọn trong giao diện: {selected_test_id}."

    run_id = uuid4().hex[:12]
    started_at = datetime.now(timezone.utc).isoformat()
    started = time.time()
    try:
        trace = run_react_agent(agent_query, provider, mcp_server)
    except Exception as exc:
        return jsonify({
            "error": "Agent không thể hoàn tất lượt chạy.",
            "detail": str(exc),
            "run": {"run_id": run_id, "status": "ERROR", "started_at": started_at}
        }), 500

    metadata = _provider_metadata()
    metadata.update({
        "run_id": run_id,
        "status": "SUCCESS" if trace and trace[-1].get("action_type") == "FINAL_ANSWER" else "INCOMPLETE",
        "started_at": started_at,
        "duration_ms": round((time.time() - started) * 1000, 2),
        "step_count": len(trace),
        "fallback_used": any(step.get("fallback_used", False) for step in trace),
        "selected_test_id": selected_test_id or None
    })
    return jsonify({"trace": trace, "run": metadata, "display_query": query})


@flask_app.route("/api/reset", methods=["POST"])
def api_reset():
    reset_mock_data()
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    print("==========================================================")
    print("🖥️  WEB QA AGENT — GUI SERVER (tùy chọn)")
    print("==========================================================")
    print(f"🔌 LLM Provider: {provider.__class__.__name__}")
    print(f"🌐 MCP Server: {mcp_server.server_name}")
    print("👉 Mở trình duyệt tại: http://127.0.0.1:5000\n")
    flask_app.run(host="127.0.0.1", port=5000, debug=False)
