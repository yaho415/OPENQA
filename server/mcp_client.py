"""
MCP 클라이언트 - FastAPI에서 MCP 서버의 도구를 호출하기 위한 클라이언트

MCP 서버를 SSE 모드로 실행하고, HTTP를 통해 도구를 호출합니다.
"""

import json
import os
from typing import Optional, Dict, Any

import httpx
from dotenv import load_dotenv

load_dotenv()

MCP_SERVER_URL = os.getenv("MCP_SERVER_URL", "http://localhost:8000")


class MCPClient:
    """MCP 서버 클라이언트 (SSE 모드)"""

    def __init__(self, base_url: str = MCP_SERVER_URL):
        self.base_url = base_url.rstrip("/")
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        """HTTP 클라이언트 싱글톤"""
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=httpx.Timeout(60.0, connect=10.0),
            )
        return self._client

    async def call_tool(
        self, tool_name: str, arguments: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        MCP 서버의 도구를 호출

        Args:
            tool_name: 도구 이름 (예: "recommend_projects")
            arguments: 도구 인자

        Returns:
            도구 실행 결과
        """
        client = await self._get_client()

        # MCP JSON-RPC 요청 형식
        request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": arguments,
            },
        }

        try:
            resp = await client.post("/sse", json=request)
            resp.raise_for_status()
            data = resp.json()

            if "error" in data:
                raise Exception(f"MCP 서버 오류: {data['error']}")

            result = data.get("result", {})
            content = result.get("content", [])

            # content가 리스트인 경우 첫 번째 항목의 text 추출
            if content and len(content) > 0:
                text = content[0].get("text", "")
                try:
                    # JSON 문자열인 경우 파싱
                    return json.loads(text)
                except json.JSONDecodeError:
                    return {"result": text}

            return result

        except httpx.HTTPError as e:
            raise Exception(f"MCP 서버 연결 실패: {e}")

    async def recommend_projects(self, query: str, max_results: int = 3) -> Dict:
        """유사 프로젝트 추천"""
        result = await self.call_tool(
            "recommend_projects", {"query": query, "max_results": max_results}
        )
        return result

    async def close(self):
        """클라이언트 종료"""
        if self._client:
            await self._client.aclose()
            self._client = None


# 싱글톤 인스턴스
_mcp_client: Optional[MCPClient] = None


def get_mcp_client() -> MCPClient:
    """MCP 클라이언트 싱글톤"""
    global _mcp_client
    if _mcp_client is None:
        _mcp_client = MCPClient()
    return _mcp_client
