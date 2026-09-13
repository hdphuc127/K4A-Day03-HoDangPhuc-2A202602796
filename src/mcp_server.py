"""
🔌 MODEL CONTEXT PROTOCOL (MCP) SERVER MODULE
Mô phỏng kiến trúc MCP Server (Client-Server Architecture) cung cấp công cụ chuẩn hóa
cho Web QA Test Case Lookup & Retest Ticket Agent.
"""

import json
import sys
from typing import Dict, Any, List
from tools import TOOLS_SCHEMA, dispatch_tool_call

if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

class MCPQAServer:
    """
    Giả lập MCP Server tuân thủ chuẩn giao thức Model Context Protocol
    """
    def __init__(self, server_name: str = "webqa-retest-mcp-server"):
        self.server_name = server_name
        self.version = "2026.1.0"

    def list_tools(self) -> List[Dict[str, Any]]:
        """Trả về danh sách các Tools chuẩn giao thức MCP"""
        return TOOLS_SCHEMA

    def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """
        Thực thi request gọi Tool theo chuẩn MCP JSON-RPC
        """
        raw_result = dispatch_tool_call(tool_name, arguments)
        content = json.loads(raw_result)
        return {
            "jsonrpc": "2.0",
            "server": self.server_name,
            "tool": tool_name,
            "result": content
        }


if __name__ == "__main__":
    print("==========================================================")
    print("🔌 KIỂM THỬ ĐỘC LẬP MCP SERVER (webqa-retest-mcp-server)")
    print("==========================================================")

    server = MCPQAServer()
    tools = server.list_tools()
    print(f"✅ Khởi tạo thành công MCP Server: {server.server_name} (Version: {server.version})")
    print(f"📦 Số lượng Tools công bố qua MCP: {len(tools)}")
    for t in tools:
        print(f"   - {t['name']}")

    hit = server.call_tool("lookup_test_case", {"test_id": "TC-MOB-202"})
    print(f"\n🧪 [Smoke Test] lookup_test_case('TC-MOB-202') ->")
    print(f"   {json.dumps(hit, ensure_ascii=False)}")

    miss = server.call_tool("lookup_test_case", {"test_id": "TC-WEB-999"})
    print(f"\n🧪 [Smoke Test] lookup_test_case('TC-WEB-999') ->")
    print(f"   {json.dumps(miss, ensure_ascii=False)}")

    if hit.get("result", {}).get("status") == "SUCCESS" and miss.get("result", {}).get("status") == "NOT_FOUND":
        print("\n✅ MCP Server call_tool() hoạt động chính xác.")
    else:
        print("\n⚠️ MCP Server call_tool() trả về kết quả không như mong đợi!")
