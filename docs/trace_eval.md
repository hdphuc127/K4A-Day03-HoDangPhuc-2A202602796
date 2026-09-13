# 📊 BÁO CÁO THU HOẠCH NGHIỆM THU BÀI LAB 3 (BƯỚC 3 — SUBMISSION ARTIFACT)

> **Họ và Tên Học viên:** Hồ Đăng Phúc  
> **Mã Sinh Viên / Mã Học viên:** 2A202602796  
> **Chủ đề Lựa chọn:** Trợ lý Tra cứu Kết quả Test Case & Tạo Phiếu Retest (Web QA Assistant) — Đề tài Mở (Lĩnh vực 5, `DANH_SACH_DE_TAI.md`)

---

## 1. BẢNG CHẤM ĐIỂM AGENTIC FIT SCORING MATRIX (ĐÁNH GIÁ CHỦ ĐỀ)

| Tiêu chí Đánh giá | Mức độ (1 - 5) | Giải trình chi tiết lý do chọn điểm |
| :--- | :---: | :--- |
| **1. Multi-step Reasoning** | 4 / 5 | Luồng xử lý đi qua nhiều bước suy luận nối tiếp: định danh test_id trong câu hỏi → `lookup_test_case` → đánh giá `run_status`/`retest_allowed`/`existing_retest_ticket` từ Observation → quyết định có tạo `create_retest_ticket` hay không → tổng hợp Final Answer. Không đạt 5/5 vì chuỗi suy luận bị chặn ở tối đa 2-3 bước cho mỗi câu hỏi, không có kế hoạch phân rã mục tiêu nhiều tầng. |
| **2. Tool Interaction** | 5 / 5 | Không thể trả lời chính xác nếu thiếu Tool: cả 4 Tool (`lookup_test_case`, `list_test_cases`, `create_retest_ticket`, `check_retest_ticket_status`) đều bắt buộc round-trip qua MCP Server tới "cơ sở dữ liệu" test case/ticket; không có kiến thức tĩnh nào thay thế được dữ liệu thời gian thực này. |
| **3. Dynamic Decision** | 5 / 5 | Quyết định gọi `create_retest_ticket` hay từ chối hoàn toàn phụ thuộc vào các trường trả về từ `lookup_test_case` ở bước trước (`retest_allowed`, `existing_retest_ticket`, `status=NOT_FOUND`) — một nhánh rẽ động kinh điển, không thể xác định trước khi có Observation. |
| **4. Long Horizon Goal** | 3 / 5 | Mỗi câu hỏi là một phiên xử lý ngắn, tự chứa (1-3 bước), không có trạng thái mục tiêu xuyên suốt nhiều phiên hội thoại hay nhiều ngày — phù hợp mức trung bình, không phải mức cao nhất. |
| **TỔNG ĐIỂM AGENTIC FIT** | **17 / 20** | *Nếu tổng điểm > 12/20: Bài toán rất phù hợp triển khai Agentic System.* |

---

## 2. TRÍCH XUẤT KẾT QUẢ WATERFALL TRACE LOG (SAU KHI CHẠY TEST SUITE TRÊN API THẬT)

> ✅ **Đã kết nối LLM thật:** `LLM_PROVIDER=gemini`, model `gemini-2.5-flash`, chạy qua `python src/app.py --all`. Toàn bộ đoạn trích dưới đây là log THẬT do Gemini sinh ra (không chỉnh sửa thủ công), lấy từ `docs/trace_waterfall.json`.

Đoạn trích dưới là toàn bộ 3 bước (TOOL_EXECUTION → TOOL_EXECUTION → FINAL_ANSWER) của **TC03** — kịch bản suy luận đa bước: `lookup_test_case` xác nhận test case đủ điều kiện, sau đó Gemini tự quyết định gọi `create_retest_ticket`, rồi tổng hợp Final Answer:

```json
[
  {
    "step": 1,
    "query": "Check TC-MOB-202. If it is a confirmed high-severity failing test, retest is allowed, and no ticket exists, create a retest ticket requested by Nguyễn Văn An.",
    "action_type": "TOOL_EXECUTION",
    "thought": "Gemini quyết định gọi công cụ 'lookup_test_case' với tham số: {\"test_id\": \"TC-MOB-202\"}",
    "tool_name": "lookup_test_case",
    "arguments": { "test_id": "TC-MOB-202" },
    "observation": {
      "status": "SUCCESS",
      "test_id": "TC-MOB-202",
      "platform": "Mobile",
      "failure_category": "element_not_found",
      "severity": "high",
      "run_status": "failed_confirmed",
      "failure_summary": "Nút 'Xác nhận đơn hàng' không được tìm thấy trên màn hình Checkout ở phiên bản Android mới nhất; lỗi tái hiện ổn định qua 3 lần chạy.",
      "retest_allowed": true,
      "existing_retest_ticket": null
    },
    "latency_ms": 1224.01
  },
  {
    "step": 2,
    "query": "Check TC-MOB-202. If it is a confirmed high-severity failing test, retest is allowed, and no ticket exists, create a retest ticket requested by Nguyễn Văn An.",
    "action_type": "TOOL_EXECUTION",
    "thought": "Gemini quyết định gọi công cụ 'create_retest_ticket' với tham số: {\"reason\": \"Test case TC-MOB-202 thất bại với mức độ nghiêm trọng high, phân loại lỗi element_not_found...\", \"test_id\": \"TC-MOB-202\", \"requested_by\": \"Nguyễn Văn An\", \"priority\": \"High\"}",
    "tool_name": "create_retest_ticket",
    "arguments": {
      "reason": "Test case TC-MOB-202 thất bại với mức độ nghiêm trọng high, phân loại lỗi element_not_found. Chi tiết: Nút 'Xác nhận đơn hàng' không được tìm thấy trên màn hình Checkout ở phiên bản Android mới nhất; lỗi tái hiện ổn định qua 3 lần chạy.",
      "test_id": "TC-MOB-202",
      "requested_by": "Nguyễn Văn An",
      "priority": "High"
    },
    "observation": {
      "status": "SUCCESS",
      "ticket_id": "RTK-MOB-202",
      "test_id": "TC-MOB-202",
      "priority": "High",
      "requested_by": "Nguyễn Văn An",
      "message": "Đã tạo phiếu retest 'RTK-MOB-202' cho test case 'TC-MOB-202' (priority: High)."
    },
    "latency_ms": 1262.9
  },
  {
    "step": 3,
    "query": "Check TC-MOB-202. If it is a confirmed high-severity failing test, retest is allowed, and no ticket exists, create a retest ticket requested by Nguyễn Văn An.",
    "action_type": "FINAL_ANSWER",
    "thought": "Gemini phản hồi trực tiếp bằng văn bản (không cần gọi công cụ).",
    "output": "Dựa trên kết quả thực thi các bước kiểm tra và tạo phiếu retest: ... Mã phiếu: RTK-MOB-202, Độ ưu tiên: High, Người yêu cầu: Nguyễn Văn An. (xem toàn văn trong docs/trace_waterfall.json)",
    "latency_ms": 2218.07
  }
]
```

---

## 3. TỔNG KẾT KẾT QUẢ NGHIỆM THU & NỘP BÀI

- [x] Đã điền API Key thật trong `.env` và xác nhận Agent chạy mượt mà trên LLM API thật (Gemini, model `gemini-2.5-flash`, provider log hiển thị `GeminiProvider`).
- **Tổng số Test Cases đã chạy thành công:** 7 / 7 test cases (5 kịch bản bắt buộc TC01-TC05 + 2 kịch bản bổ sung TC06-TC07 minh hoạ `list_test_cases`/`check_retest_ticket_status`).
- **Số lượt gọi Tool qua MCP Server chính xác:** 7 lượt trên toàn bộ 7 test case (4× `lookup_test_case`, 1× `create_retest_ticket`, 1× `list_test_cases`, 1× `check_retest_ticket_status`); không có lượt gọi `create_retest_ticket` nào xảy ra sai (TC04 bị từ chối do trùng phiếu, TC05 bị từ chối do NOT_FOUND, đúng như kỳ vọng).
- **Ghi chú xác thực:** Kết quả trên chạy với LLM thật (Gemini). Runbook cũng đã được xác minh riêng với `MockOfflineProvider` (offline/mock, `LLM_PROVIDER=mock`) để kiểm tra logic quyết định trước khi tốn API call thật — kết quả mock khớp 100% với kỳ vọng của cả 7 test case.
- **Kết quả đẩy Repo nộp bài:** [ ] Đã Commit và Push mã nguồn thành công lên GitHub cá nhân. *(Bước này do học viên tự thực hiện sau khi rà soát lại `git diff`.)*

---

> ✅ **HOÀN TẤT NỘP BÀI:** Sao chép đường link GitHub Repository cá nhân của bạn và dán vào ô nộp bài trên hệ thống LMS VLearn để hoàn tất Bài Lab 3!
