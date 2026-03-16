"""
MCP 서버 - OpenQA+ 유사 프로젝트 추천 서비스

MCP(Model Context Protocol) 표준을 따르는 서버로,
AI 클라이언트(Cursor, Claude Desktop 등)가 도구로 사용할 수 있습니다.

도구(Tools):
  - recommend_projects: 유사 프로젝트 추천 (BGE-M3 벡터 임베딩 + pgvector)
  - update_projects_from_excel: Excel 파일로 프로젝트 현황 업데이트
"""

import asyncio
import json
import os
import sys
import time
from typing import Optional

# 프로젝트 루트를 sys.path에 추가
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

load_dotenv()

from mcp.server.fastmcp import FastMCP

from src.case_recommender import CaseRecommender
from src.keyword_extractor import KeywordExtractor
from src.database.db import get_database
from src.mcp_tools import recommend_projects_tool, update_projects_from_excel

# ──────────────────────────────────────────────────────────
# MCP 서버 인스턴스 생성
# ──────────────────────────────────────────────────────────
mcp = FastMCP(
    name="openqa-project-recommender",
    instructions="""OpenQA+ 유사 프로젝트 추천 MCP 서버입니다.

이 서버는 축적된 프로젝트 데이터베이스에서 유사한 프로젝트를 찾아 추천해주는 도구를 제공합니다.

사용 가능한 도구:
1. recommend_projects - 프로젝트 설명을 입력하면 벡터 유사도 기반으로 유사 프로젝트를 추천합니다.
2. update_projects_from_excel - Excel 파일(xlsx)을 업로드하여 프로젝트 현황을 업데이트합니다.

사용자가 프로젝트 추천을 요청하면 recommend_projects 도구를 사용하세요.
사용자가 프로젝트 현황 파일 반영을 요청하면 update_projects_from_excel 도구를 사용하세요.
""",
)

# ──────────────────────────────────────────────────────────
# 공유 인스턴스
# ──────────────────────────────────────────────────────────
case_recommender = CaseRecommender()
keyword_extractor = KeywordExtractor()


# ──────────────────────────────────────────────────────────
# Tool 1: 유사 프로젝트 추천 (벡터 기반)
# ──────────────────────────────────────────────────────────
@mcp.tool(
    name="recommend_projects",
    description="프로젝트 설명을 입력하면 벡터 유사도 기반으로 유사한 프로젝트를 추천합니다. "
    "BGE-M3 임베딩과 pgvector 코사인 유사도를 사용합니다.",
)
async def recommend_projects(
    query: str,
    max_results: int = 5,
) -> str:
    """유사 프로젝트 추천

    Args:
        query: 찾고자 하는 프로젝트에 대한 설명 (예: "금융권 차세대 시스템 구축")
        max_results: 추천할 최대 프로젝트 수 (기본값: 5)

    Returns:
        추천된 프로젝트 목록 (JSON)
    """
    start = time.time()

    result = await recommend_projects_tool(query, max_results)

    elapsed = time.time() - start
    result["timingSeconds"] = round(elapsed, 2)

    return json.dumps(result, ensure_ascii=False, indent=2)


# ──────────────────────────────────────────────────────────
# Tool 2: Excel 파일로 프로젝트 현황 업데이트
# ──────────────────────────────────────────────────────────
@mcp.tool(
    name="update_projects_from_excel",
    description="Excel 파일(xlsx)을 읽어서 프로젝트 현황(project 테이블)을 업데이트합니다. "
    "project_code 기준으로 변경된 데이터가 있으면 업데이트하고, updated_at을 현재 시간으로 변경합니다. "
    "업데이트된 데이터는 BGE-M3를 통해 임베딩을 생성하여 벡터값도 업데이트합니다. "
    "Excel 파일에는 project_code, project_name 컬럼이 필수입니다.",
)
async def update_projects_from_excel_tool(
    file_path: str,
) -> str:
    """Excel 파일로 프로젝트 현황 업데이트

    Args:
        file_path: 업데이트할 Excel 파일의 경로 (절대 경로 또는 상대 경로)

    Returns:
        업데이트 결과 (JSON)
    """
    result = await update_projects_from_excel(file_path)
    return json.dumps(result, ensure_ascii=False, indent=2)


# ──────────────────────────────────────────────────────────
# 서버 실행
# ──────────────────────────────────────────────────────────
if __name__ == "__main__":
    # Windows cp949 인코딩 문제 해결
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    print("[MCP] OpenQA+ 유사 프로젝트 추천 MCP 서버 시작")
    print(f"[MCP] 전송 방식: stdio")
    print(f"[MCP] 제공 도구: recommend_projects, update_projects_from_excel")

    mcp.run(transport="stdio")
