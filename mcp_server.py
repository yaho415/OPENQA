"""
OpenQA+ MCP 서버 - 유사 프로젝트 추천 도구 제공 (Qwen 2.5 통합)

MCP(Model Context Protocol) 서버로, AI 모델(Cursor, Claude Desktop 등)이
프로젝트 추천 기능을 도구(Tool)로 사용할 수 있게 합니다.

Qwen 2.5 통합:
  - Qwen 2.5를 Ollama를 통해 호출하여 프로젝트 관련 질문에 답변
  - Qwen 2.5가 자동으로 recommend_projects 도구를 호출할 수 있도록 Tool Calling 지원
  - 대화형 AI 어시스턴트 기능 제공

사용 방법:
  1. Cursor 연동:  .cursor/mcp.json 설정 후 Cursor에서 자동 연결
  2. 직접 실행:    python mcp_server.py
  3. SSE 모드:     python mcp_server.py --sse (HTTP 서버 모드)

제공 도구:
  - recommend_projects : 유사 프로젝트 벡터 검색 + 추천 (BGE-M3 + pgvector)
  - extract_keywords   : TF-IDF 기반 키워드 추출
  - search_by_keyword  : 키워드 텍스트 검색
  - get_project_stats  : DB 통계 조회
  - get_project_detail : 프로젝트 상세 조회
  - chat_with_qwen     : Qwen 2.5 기반 대화형 AI (프로젝트 관련 질문 응답)
"""

import json
import os
import sys
import time
from typing import Optional

# 프로젝트 루트를 sys.path에 추가
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from mcp.server.fastmcp import FastMCP
from dotenv import load_dotenv
import httpx

from src.case_recommender import CaseRecommender
from src.keyword_extractor import KeywordExtractor
from src.vector_embedder import get_vector_embedder
from src.database.db import get_database
from src.mcp_tools import recommend_projects_tool  # 공통 도구 함수 사용

load_dotenv()

# ──────────────────────────────────────────────────────────
# 환경 변수
# ──────────────────────────────────────────────────────────
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
QWEN_MODEL = os.getenv("QWEN_MODEL", "qwen2.5")

# ──────────────────────────────────────────────────────────
# MCP 서버 인스턴스 생성
# ──────────────────────────────────────────────────────────
mcp = FastMCP(
    "openqa-recommender",
    instructions=(
        "OpenQA+ 유사 프로젝트 추천 MCP 서버입니다. "
        "사용자가 프로젝트 사례를 찾거나, 유사한 프로젝트를 추천받고 싶을 때 "
        "recommend_projects 도구를 사용하세요. "
        "키워드 추출, 키워드 검색, 통계 조회, 상세 조회 도구도 제공합니다. "
        "Qwen 2.5 AI와 대화하여 프로젝트 관련 질문에 답변받을 수 있습니다."
    ),
)

# 핵심 모듈 인스턴스
_recommender = CaseRecommender()
_extractor = KeywordExtractor()

# Qwen 2.5 클라이언트 (재사용)
_qwen_client: Optional[httpx.AsyncClient] = None


def get_qwen_client() -> httpx.AsyncClient:
    """Qwen 2.5 클라이언트 싱글톤"""
    global _qwen_client
    if _qwen_client is None:
        _qwen_client = httpx.AsyncClient(
            base_url=OLLAMA_URL,
            timeout=httpx.Timeout(120.0, connect=10.0),
        )
    return _qwen_client


# ──────────────────────────────────────────────────────────
# Tool 1: 유사 프로젝트 추천 (벡터 기반)
# ──────────────────────────────────────────────────────────
@mcp.tool()
async def recommend_projects(query: str, max_results: int = 3) -> str:
    """사용자의 요구사항과 유사한 프로젝트를 벡터 유사도 기반으로 검색하고 추천합니다.

    BGE-M3 임베딩 모델로 텍스트를 1024차원 벡터로 변환한 뒤,
    pgvector 코사인 유사도로 가장 유사한 프로젝트를 찾아 반환합니다.

    Args:
        query: 검색할 프로젝트 설명 (예: "금융권 차세대 시스템 구축", "공공기관 인사급여 시스템")
        max_results: 반환할 최대 결과 수 (기본값: 3, 최대: 10)

    Returns:
        유사 프로젝트 목록 (JSON) - 프로젝트명, 등급, 부서, 업종, 사업개요, 유사도 점수, 매칭 키워드 포함
    """
    # 공통 도구 함수 사용
    result = await recommend_projects_tool(query, max_results)
    return json.dumps(result, ensure_ascii=False, indent=2)


# ──────────────────────────────────────────────────────────
# Tool 2: 키워드 추출
# ──────────────────────────────────────────────────────────
@mcp.tool()
def extract_keywords(text: str, max_keywords: int = 5) -> str:
    """텍스트에서 TF-IDF 기반으로 주요 키워드를 추출합니다.

    한국어/영어 불용어를 제거하고, 단어 빈도와 길이 보너스를 결합하여
    가장 의미 있는 키워드를 추출합니다.

    Args:
        text: 키워드를 추출할 텍스트
        max_keywords: 추출할 최대 키워드 수 (기본값: 5)

    Returns:
        추출된 키워드 배열 (JSON)
    """
    keywords = _extractor.extract_keywords(text, max_keywords)
    return json.dumps(keywords, ensure_ascii=False)


# ──────────────────────────────────────────────────────────
# Tool 3: 키워드 텍스트 검색
# ──────────────────────────────────────────────────────────
@mcp.tool()
def search_by_keyword(keyword: str) -> str:
    """키워드로 프로젝트를 텍스트 검색합니다.

    프로젝트명, 사업개요, 부서명, 업종, 키워드 필드에서
    해당 키워드가 포함된 프로젝트를 찾습니다.
    벡터 검색과 달리 정확한 텍스트 매칭을 수행합니다.

    Args:
        keyword: 검색할 키워드 (예: "ERP", "금융", "제조")

    Returns:
        검색된 프로젝트 목록 (JSON, 최대 10건)
    """
    db = get_database()
    cases = db.search_cases_by_keyword(keyword)

    results = []
    for case in cases[:10]:
        overview = case.business_overview.replace("프로젝트 배경 및 요약: ", "")
        results.append({
            "id": case.id,
            "projectName": case.project_name,
            "grade": case.grade,
            "department": case.department,
            "industry": case.industry,
            "businessOverview": overview[:200] + "..." if len(overview) > 200 else overview,
            "keywords": case.keywords,
        })

    if not results:
        return f"'{keyword}' 키워드로 검색된 프로젝트가 없습니다."

    return json.dumps(results, ensure_ascii=False, indent=2)


# ──────────────────────────────────────────────────────────
# Tool 4: 프로젝트 DB 통계
# ──────────────────────────────────────────────────────────
@mcp.tool()
def get_project_stats() -> str:
    """프로젝트 데이터베이스의 통계 정보를 반환합니다.

    전체 프로젝트 수, 벡터 임베딩 완료 수, 업종별 분포, 등급별 분포 등을
    한눈에 확인할 수 있습니다.

    Returns:
        프로젝트 통계 (JSON) - 총 프로젝트 수, 임베딩 상태, 업종/등급 분포
    """
    db = get_database()
    embedding_status = db.get_embedding_status()
    all_cases = db.get_all_cases()

    industry_counts = {}
    grade_counts = {"A": 0, "B": 0, "C": 0}
    for case in all_cases:
        industry_counts[case.industry] = industry_counts.get(case.industry, 0) + 1
        if case.grade in grade_counts:
            grade_counts[case.grade] += 1

    stats = {
        "totalProjects": embedding_status["total"],
        "withEmbedding": embedding_status["with_embedding"],
        "withoutEmbedding": embedding_status["without_embedding"],
        "industryDistribution": industry_counts,
        "gradeDistribution": grade_counts,
    }

    return json.dumps(stats, ensure_ascii=False, indent=2)


# ──────────────────────────────────────────────────────────
# Tool 5: 프로젝트 상세 조회
# ──────────────────────────────────────────────────────────
@mcp.tool()
def get_project_detail(project_id: str) -> str:
    """프로젝트 ID로 상세 정보를 조회합니다.

    프로젝트명, 등급, 부서, 업종, 사업개요, 키워드, 태그 등
    해당 프로젝트의 모든 정보를 반환합니다.

    Args:
        project_id: 프로젝트 고유 ID

    Returns:
        프로젝트 상세 정보 (JSON)
    """
    db = get_database()
    case = db.get_case_by_id(project_id)

    if not case:
        return f"ID '{project_id}'에 해당하는 프로젝트를 찾을 수 없습니다."

    overview = case.business_overview.replace("프로젝트 배경 및 요약: ", "")
    result = case.to_dict()
    result["businessOverview"] = overview

    return json.dumps(result, ensure_ascii=False, indent=2)


# ──────────────────────────────────────────────────────────
# Tool 6: Qwen 2.5 대화 (프로젝트 관련 질문 응답)
# ──────────────────────────────────────────────────────────
@mcp.tool()
async def chat_with_qwen(
    question: str,
    context: Optional[str] = None,
) -> str:
    """Qwen 2.5 AI 모델과 대화합니다. 프로젝트 관련 질문, 일반 상담, 기술 자문 등에 활용할 수 있습니다.

    Qwen 2.5는 Ollama를 통해 호출되며, 프로젝트 관련 전문 지식을 바탕으로 답변합니다.
    context 파라미터에 프로젝트 검색 결과를 전달하면 더 정확한 답변을 받을 수 있습니다.

    Args:
        question: 질문 내용 (예: "ERP 시스템 구축 시 주의사항은?", "금융권 프로젝트의 특징은?")
        context: 추가 맥락 정보 (프로젝트 검색 결과 등) - 선택사항

    Returns:
        Qwen 2.5의 답변 (텍스트)
    """
    system_prompt = """너는 OpenQA+ Copilot이야. 프로젝트 관련 전문 AI 어시스턴트야.
- 항상 한국어로 답변해.
- 답변은 전문적이고 구체적으로 해줘.
- 프로젝트 기획, 시스템 구축, IT 컨설팅 관련 질문에 강점이 있어.
- 사용자가 프로젝트를 찾고 싶어하면 recommend_projects 도구를 사용하라고 안내해줘.
"""

    messages = [{"role": "system", "content": system_prompt}]

    if context:
        messages.append({
            "role": "system",
            "content": f"참고 정보:\n{context}",
        })

    messages.append({"role": "user", "content": question})

    try:
        client = get_qwen_client()
        resp = await client.post(
            "/api/chat",
            json={
                "model": QWEN_MODEL,
                "messages": messages,
                "stream": False,
                "options": {
                    "temperature": 0.7,
                    "num_predict": 1024,
                },
            },
        )
        resp.raise_for_status()
        data = resp.json()
        answer = data.get("message", {}).get(
            "content", "죄송합니다, 응답을 생성하지 못했습니다."
        )
        return answer

    except httpx.HTTPError as e:
        return f"Qwen 2.5 모델 호출 실패: {e}\nOllama가 실행 중인지 확인해주세요. (ollama serve 또는 Ollama 앱 실행)"
    except Exception as e:
        return f"오류 발생: {e}"


# ──────────────────────────────────────────────────────────
# 서버 실행
# ──────────────────────────────────────────────────────────
if __name__ == "__main__":
    # Windows cp949 인코딩 문제 해결
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    transport = "stdio"
    if "--sse" in sys.argv:
        transport = "sse"
        print("[MCP] SSE 모드로 실행합니다 (HTTP 서버)", file=sys.stderr)
    else:
        print("[MCP] stdio 모드로 실행합니다 (Cursor/Claude Desktop 연동)", file=sys.stderr)

    print("[MCP] OpenQA+ MCP 서버 시작...", file=sys.stderr)
    print(f"[MCP] Qwen 모델: {QWEN_MODEL}", file=sys.stderr)
    print(f"[MCP] Ollama URL: {OLLAMA_URL}", file=sys.stderr)
    print("[MCP] 제공 도구:", file=sys.stderr)
    print("  - recommend_projects: 유사 프로젝트 벡터 검색 + 추천", file=sys.stderr)
    print("  - extract_keywords: TF-IDF 키워드 추출", file=sys.stderr)
    print("  - search_by_keyword: 키워드 텍스트 검색", file=sys.stderr)
    print("  - get_project_stats: DB 통계 조회", file=sys.stderr)
    print("  - get_project_detail: 프로젝트 상세 조회", file=sys.stderr)
    print("  - chat_with_qwen: Qwen 2.5 기반 대화형 AI", file=sys.stderr)

    mcp.run(transport=transport)
