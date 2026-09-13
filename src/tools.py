"""
🛠️ TOOL DEFINITIONS & EXECUTION BACKEND
Web QA Test Case Lookup & Retest Ticket Agent — Tool Schemas (JSON Schema) và Execution Layer cho MCP Server.
"""

import copy
import json
import math
import re
import unicodedata
from typing import Dict, Any, Optional

# ==============================================================================
# 1. KHAI BÁO TOOL SCHEMAS CHUẨN NATIVE JSON SCHEMA
# ==============================================================================

TOOLS_SCHEMA = [
    {
        "name": "lookup_test_case",
        "description": (
            "Tra cứu chi tiết một test case theo mã test_id. Trả về nền tảng (platform), phân loại lỗi, "
            "mức độ nghiêm trọng, trạng thái lần chạy gần nhất (run_status), tóm tắt lỗi (failure_summary), "
            "và liệu test case có đủ điều kiện tạo phiếu retest hay đã có phiếu retest hay chưa."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "test_id": {
                    "type": "string",
                    "description": "Mã định danh test case, ví dụ 'TC-WEB-101' hoặc 'TC-MOB-202'."
                }
            },
            "required": ["test_id"]
        }
    },
    {
        "name": "list_test_cases",
        "description": (
            "Liệt kê/tìm kiếm các test case theo từ khóa và bộ lọc tùy chọn. "
            "Dùng khi người dùng không nhớ test_id hoặc hỏi theo mô tả lỗi, nền tảng, trạng thái, severity."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Từ khóa tự do khớp với test_id, tiêu đề, loại lỗi hoặc mô tả lỗi."
                },
                "run_status": {
                    "type": "string",
                    "enum": ["under_investigation", "failed_confirmed", "passed", "flaky"],
                    "description": "Lọc theo trạng thái lần chạy gần nhất (tùy chọn)."
                },
                "platform": {
                    "type": "string",
                    "enum": ["Web", "Mobile"],
                    "description": "Lọc theo nền tảng (tùy chọn)."
                },
                "severity": {
                    "type": "string",
                    "enum": ["low", "medium", "high", "critical"],
                    "description": "Lọc theo mức độ nghiêm trọng (tùy chọn)."
                },
                "failure_category": {
                    "type": "string",
                    "description": "Lọc theo phân loại lỗi (tùy chọn)."
                },
                "retest_allowed": {
                    "type": "boolean",
                    "description": "Chỉ lấy case được/không được phép retest."
                },
                "has_ticket": {
                    "type": "boolean",
                    "description": "Chỉ lấy case đã có/chưa có phiếu retest."
                },
                "limit": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 50,
                    "description": "Số kết quả tối đa, mặc định 20."
                }
            },
            "required": []
        }
    },
    {
        "name": "create_retest_ticket",
        "description": (
            "Tạo phiếu Retest (yêu cầu chạy lại kiểm thử) cho một test case đã được xác nhận lỗi và đủ điều kiện retest. "
            "Chỉ gọi tool này SAU KHI đã lookup_test_case và xác nhận test case tồn tại, retest_allowed=true, "
            "và chưa có existing_retest_ticket."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "test_id": {"type": "string", "description": "Mã test case cần tạo phiếu retest."},
                "requested_by": {"type": "string", "description": "Họ tên người yêu cầu tạo phiếu retest."},
                "reason": {
                    "type": "string",
                    "description": (
                        "Lý do tạo retest, chỉ được suy ra từ dữ liệu lookup_test_case "
                        "(failure_category, severity, failure_summary) — không tự bịa."
                    )
                },
                "priority": {
                    "type": "string",
                    "enum": ["Low", "Medium", "High", "Critical"],
                    "description": "Độ ưu tiên xử lý phiếu, suy ra từ severity của test case."
                }
            },
            "required": ["test_id", "requested_by", "reason", "priority"]
        }
    },
    {
        "name": "check_retest_ticket_status",
        "description": (
            "Tra cứu trạng thái một phiếu retest đã tồn tại theo mã ticket_id (dù được tạo trong phiên này hay đã "
            "tồn tại từ trước)."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "ticket_id": {
                    "type": "string",
                    "description": "Mã phiếu retest cần tra cứu, ví dụ 'RTK-MOB-204'."
                }
            },
            "required": ["ticket_id"]
        }
    }
]

# ==============================================================================
# 2. MÔ PHỎNG DỮ LIỆU & HÀM THỰC THI TOOL (EXECUTION LAYER)
# ==============================================================================

TEST_CASE_DATABASE = {
    "TC-WEB-101": {
        "title": "Checkout timeout đang điều tra",
        "platform": "Web",
        "failure_category": "under_investigation",
        "severity": "medium",
        "run_status": "under_investigation",
        "failure_summary": "Checkout flow test đang được điều tra: log ghi nhận timeout không ổn định ở bước thanh toán, chưa xác nhận là lỗi thật.",
        "retest_allowed": False,
        "existing_retest_ticket": None
    },
    "TC-MOB-202": {
        "title": "Không tìm thấy nút Xác nhận đơn hàng",
        "platform": "Mobile",
        "failure_category": "element_not_found",
        "severity": "high",
        "run_status": "failed_confirmed",
        "failure_summary": "Nút 'Xác nhận đơn hàng' không được tìm thấy trên màn hình Checkout ở phiên bản Android mới nhất; lỗi tái hiện ổn định qua 3 lần chạy.",
        "retest_allowed": True,
        "existing_retest_ticket": None
    },
    "TC-WEB-103": {
        "title": "Staging timeout do môi trường",
        "platform": "Web",
        "failure_category": "environment_flake",
        "severity": "low",
        "run_status": "failed_confirmed",
        "failure_summary": "Lỗi do môi trường staging quá tải gây timeout ngẫu nhiên, không phải lỗi sản phẩm thực sự; đã xác nhận qua log hạ tầng.",
        "retest_allowed": False,
        "existing_retest_ticket": None
    },
    "TC-MOB-204": {
        "title": "Điều hướng sai sau đăng nhập",
        "platform": "Mobile",
        "failure_category": "wrong_navigation",
        "severity": "high",
        "run_status": "failed_confirmed",
        "failure_summary": "Sau khi đăng nhập, ứng dụng điều hướng sai màn hình (Trang chủ thay vì Giỏ hàng đã lưu) trên iOS.",
        "retest_allowed": True,
        "existing_retest_ticket": "RTK-MOB-204"
    }
}

RETEST_TICKETS = {
    "RTK-MOB-204": {
        "ticket_id": "RTK-MOB-204",
        "test_id": "TC-MOB-204",
        "requested_by": "Trần Thị Bình",
        "reason": "wrong_navigation (severity: high) - Sau khi đăng nhập, ứng dụng điều hướng sai màn hình trên iOS.",
        "priority": "High",
        "ticket_status": "OPEN"
    }
}

_VALID_PRIORITIES = {"Low", "Medium", "High", "Critical"}

_INITIAL_TEST_CASE_DATABASE = copy.deepcopy(TEST_CASE_DATABASE)
_INITIAL_RETEST_TICKETS = copy.deepcopy(RETEST_TICKETS)


def reset_mock_data() -> None:
    """Khôi phục TEST_CASE_DATABASE và RETEST_TICKETS về trạng thái ban đầu (dùng cho phiên demo GUI)."""
    TEST_CASE_DATABASE.clear()
    TEST_CASE_DATABASE.update(copy.deepcopy(_INITIAL_TEST_CASE_DATABASE))
    RETEST_TICKETS.clear()
    RETEST_TICKETS.update(copy.deepcopy(_INITIAL_RETEST_TICKETS))


def execute_lookup_test_case(test_id: str) -> str:
    """Thực thi tra cứu test case theo mã test_id"""
    if not test_id or not str(test_id).strip():
        return json.dumps({"status": "VALIDATION_ERROR", "message": "test_id là bắt buộc."}, ensure_ascii=False)
    key = str(test_id).strip().upper()
    case = TEST_CASE_DATABASE.get(key)
    if not case:
        return json.dumps({
            "status": "NOT_FOUND", "test_id": key,
            "message": f"Không tìm thấy test case nào với mã '{key}'."
        }, ensure_ascii=False)
    return json.dumps({"status": "SUCCESS", "test_id": key, **case}, ensure_ascii=False)


_SEARCH_STOP_WORDS = {
    "test", "case", "testcase", "tim", "kiem", "hay", "giup", "toi", "khong", "nho", "ma",
    "co", "loi", "nao", "nhung", "liet", "ke", "which", "list", "show", "find", "search", "the",
    "a", "an", "for", "with", "please", "currently"
}


def _normalize_search_text(value: Any) -> str:
    text = unicodedata.normalize("NFD", str(value or "").lower().replace("đ", "d"))
    text = "".join(char for char in text if unicodedata.category(char) != "Mn")
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def _search_tokens(query: Optional[str]) -> list:
    return [
        token for token in _normalize_search_text(query).split()
        if len(token) >= 2 and token not in _SEARCH_STOP_WORDS
    ]


def search_test_case_records(
    query: Optional[str] = None,
    run_status: Optional[str] = None,
    platform: Optional[str] = None,
    severity: Optional[str] = None,
    failure_category: Optional[str] = None,
    retest_allowed: Optional[bool] = None,
    has_ticket: Optional[bool] = None,
    limit: int = 20
) -> list:
    """Tìm test case cho cả MCP tool và Test Case Explorer của web prototype."""
    tokens = _search_tokens(query)
    normalized_query = _normalize_search_text(query)
    ranked_results = []

    for test_id, case in TEST_CASE_DATABASE.items():
        if run_status and str(case.get("run_status", "")).lower() != str(run_status).strip().lower():
            continue
        if platform and str(case.get("platform", "")).lower() != str(platform).strip().lower():
            continue
        if severity and str(case.get("severity", "")).lower() != str(severity).strip().lower():
            continue
        if failure_category and str(case.get("failure_category", "")).lower() != str(failure_category).strip().lower():
            continue
        if retest_allowed is not None and bool(case.get("retest_allowed")) != bool(retest_allowed):
            continue
        if has_ticket is not None and bool(case.get("existing_retest_ticket")) != bool(has_ticket):
            continue

        record = {"test_id": test_id, **case}
        haystack = _normalize_search_text(" ".join([
            test_id,
            case.get("title", ""),
            case.get("failure_category", ""),
            case.get("failure_summary", ""),
            case.get("platform", ""),
            case.get("run_status", "")
        ]))
        if tokens:
            score = sum(1 for token in tokens if token in haystack)
            minimum_score = 1 if len(tokens) <= 2 else max(2, math.ceil(len(tokens) * 0.6))
            if score < minimum_score:
                continue
            if normalized_query and normalized_query in haystack:
                score += len(tokens) + 2
        else:
            score = 0
        ranked_results.append((score, test_id, record))

    ranked_results.sort(key=lambda item: (-item[0], item[1]))
    try:
        safe_limit = max(1, min(int(limit), 50))
    except (TypeError, ValueError):
        safe_limit = 20
    return [record for _, _, record in ranked_results[:safe_limit]]


def execute_list_test_cases(
    query: Optional[str] = None,
    run_status: Optional[str] = None,
    platform: Optional[str] = None,
    severity: Optional[str] = None,
    failure_category: Optional[str] = None,
    retest_allowed: Optional[bool] = None,
    has_ticket: Optional[bool] = None,
    limit: int = 20
) -> str:
    """Liệt kê/tìm kiếm test case theo từ khóa và bộ lọc tùy chọn."""
    results = search_test_case_records(
        query=query,
        run_status=run_status,
        platform=platform,
        severity=severity,
        failure_category=failure_category,
        retest_allowed=retest_allowed,
        has_ticket=has_ticket,
        limit=limit
    )
    return json.dumps({"status": "SUCCESS", "count": len(results), "results": results}, ensure_ascii=False)


def execute_create_retest_ticket(test_id: str, requested_by: str, reason: str, priority: str) -> str:
    """Thực thi tạo phiếu retest, có kiểm tra trạng thái backend theo đúng thứ tự ưu tiên"""
    missing = [
        name for name, value in [
            ("test_id", test_id), ("requested_by", requested_by),
            ("reason", reason), ("priority", priority)
        ] if not value or not str(value).strip()
    ]
    if missing:
        return json.dumps({
            "status": "VALIDATION_ERROR",
            "message": f"Thiếu hoặc không hợp lệ các trường: {', '.join(missing)}"
        }, ensure_ascii=False)
    if priority not in _VALID_PRIORITIES:
        return json.dumps({
            "status": "VALIDATION_ERROR",
            "message": f"priority phải là một trong {sorted(_VALID_PRIORITIES)}"
        }, ensure_ascii=False)

    key = str(test_id).strip().upper()
    case = TEST_CASE_DATABASE.get(key)

    if not case:
        return json.dumps({
            "status": "NOT_FOUND", "test_id": key,
            "message": f"Không thể tạo phiếu retest: test case '{key}' không tồn tại."
        }, ensure_ascii=False)

    if not case.get("retest_allowed"):
        return json.dumps({
            "status": "NOT_ELIGIBLE", "test_id": key,
            "message": f"Test case '{key}' hiện chưa đủ điều kiện retest (run_status='{case.get('run_status')}')."
        }, ensure_ascii=False)

    if case.get("existing_retest_ticket"):
        return json.dumps({
            "status": "DUPLICATE_TICKET", "test_id": key,
            "existing_retest_ticket": case["existing_retest_ticket"],
            "message": f"Test case '{key}' đã có phiếu retest '{case['existing_retest_ticket']}'."
        }, ensure_ascii=False)

    ticket_id = f"RTK-{key.replace('TC-', '')}"
    case["existing_retest_ticket"] = ticket_id
    RETEST_TICKETS[ticket_id] = {
        "ticket_id": ticket_id,
        "test_id": key,
        "requested_by": requested_by,
        "reason": reason,
        "priority": priority,
        "ticket_status": "OPEN"
    }
    return json.dumps({
        "status": "SUCCESS", "ticket_id": ticket_id, "test_id": key,
        "priority": priority, "requested_by": requested_by, "reason": reason,
        "message": f"Đã tạo phiếu retest '{ticket_id}' cho test case '{key}' (priority: {priority})."
    }, ensure_ascii=False)


def execute_check_retest_ticket_status(ticket_id: str) -> str:
    """Tra cứu trạng thái một phiếu retest theo mã ticket_id"""
    if not ticket_id or not str(ticket_id).strip():
        return json.dumps({"status": "VALIDATION_ERROR", "message": "ticket_id là bắt buộc."}, ensure_ascii=False)
    key = str(ticket_id).strip().upper()
    ticket = RETEST_TICKETS.get(key)
    if not ticket:
        return json.dumps({
            "status": "NOT_FOUND", "ticket_id": key,
            "message": f"Không tìm thấy phiếu retest nào với mã '{key}'."
        }, ensure_ascii=False)
    return json.dumps({"status": "SUCCESS", **ticket}, ensure_ascii=False)


# Router gọi tool thực tế
TOOL_ROUTER = {
    "lookup_test_case": execute_lookup_test_case,
    "list_test_cases": execute_list_test_cases,
    "create_retest_ticket": execute_create_retest_ticket,
    "check_retest_ticket_status": execute_check_retest_ticket_status
}


def dispatch_tool_call(tool_name: str, arguments: Dict[str, Any]) -> str:
    """Hàm trung chuyển thực thi tool"""
    if tool_name in TOOL_ROUTER:
        try:
            return TOOL_ROUTER[tool_name](**arguments)
        except Exception as e:
            return json.dumps({"status": "EXECUTION_ERROR", "error": str(e)}, ensure_ascii=False)
    return json.dumps({"status": "UNKNOWN_TOOL", "error": f"Tool '{tool_name}' không tồn tại!"}, ensure_ascii=False)
