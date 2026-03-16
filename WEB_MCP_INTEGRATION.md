# 웹 UI → MCP 서버 연동 완료

> **구조 변경**: 웹 UI (localhost:3000)에서 프롬프트 입력 시 MCP 서버의 도구 함수가 호출되도록 구성 완료

---

## ✅ 변경 사항

### 1. 공통 도구 함수 모듈 생성 (`src/mcp_tools.py`)

MCP 서버와 FastAPI 서버에서 공통으로 사용하는 도구 함수를 분리했습니다:

```python
from src.mcp_tools import recommend_projects_tool

# 사용 예시
result = await recommend_projects_tool(query="금융권 ERP 시스템", max_results=3)
recommendations = result.get("recommendations", [])
```

### 2. FastAPI 서버 수정 (`server/app.py`)

FastAPI 서버가 MCP 도구 함수를 직접 호출하도록 변경:

```python
from src.mcp_tools import recommend_projects_tool

async def execute_recommend_projects(query: str, max_results: int = 3) -> list:
    """유사 프로젝트 검색 실행 (MCP 도구 함수 사용)"""
    result = await recommend_projects_tool(query, max_results)
    return result.get("recommendations", [])
```

### 3. MCP 서버 수정 (`mcp_server.py`)

MCP 서버도 동일한 공통 함수를 사용하도록 변경:

```python
from src.mcp_tools import recommend_projects_tool

@mcp.tool()
async def recommend_projects(query: str, max_results: int = 3) -> str:
    result = await recommend_projects_tool(query, max_results)
    return json.dumps(result, ensure_ascii=False, indent=2)
```

---

## 🔄 새로운 프로세스 흐름

```
1. 사용자가 웹 UI (localhost:3000)에서 프롬프트 입력
   "금융사업의 ERP 원가 시스템을 구축하려고 해. 유사한 프로젝트를 알려줘."

2. React 앱이 FastAPI 서버로 POST /api/chat 요청
   → server/app.py의 chat() 함수 실행

3. FastAPI 서버가 MCP 도구 함수를 직접 호출
   → execute_recommend_projects() 
   → recommend_projects_tool() (src/mcp_tools.py)
   → CaseRecommender.recommend_similar_cases()
   → BGE-M3 임베딩 + pgvector 유사도 검색

4. 결과를 웹 UI에 반환
   → 프로젝트 리스트를 테이블로 표시
```

---

## 📊 아키텍처

```
┌─────────────────────────────────────────┐
│  웹 UI (React) - localhost:3000        │
│  - 사용자 프롬프트 입력                 │
└──────────────┬──────────────────────────┘
               │ HTTP POST /api/chat
               ▼
┌─────────────────────────────────────────┐
│  FastAPI 서버 - localhost:3001          │
│  - /api/chat 엔드포인트                 │
│  - MCP 도구 함수 직접 호출              │
└──────────────┬──────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────┐
│  공통 도구 함수 (src/mcp_tools.py)      │
│  - recommend_projects_tool()            │
│  - CaseRecommender 사용                 │
└──────────────┬──────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────┐
│  핵심 로직                                │
│  - BGE-M3 임베딩 (Ollama)               │
│  - pgvector 유사도 검색 (PostgreSQL)     │
└─────────────────────────────────────────┘
```

---

## 🎯 핵심 변경점

### 이전 구조
```
웹 UI → FastAPI → CaseRecommender (직접 호출)
```

### 현재 구조
```
웹 UI → FastAPI → MCP 도구 함수 (src/mcp_tools.py) → CaseRecommender
```

**장점**:
- ✅ MCP 서버와 FastAPI 서버가 동일한 로직을 공유
- ✅ 코드 중복 제거
- ✅ MCP 서버의 도구 함수를 웹 UI에서도 사용 가능
- ✅ 유지보수 용이

---

## 🚀 사용 방법

### 1. 서버 실행

```bash
# FastAPI 서버 실행 (웹 UI용)
cd C:\Users\OPENQA
python server/app.py
```

### 2. 웹 UI 접속

브라우저에서 `http://localhost:3000` 접속

### 3. 프롬프트 입력

예시:
- "금융사업의 ERP 원가 시스템을 구축하려고 해. 유사한 프로젝트를 알려줘."
- "공공기관 인사급여 시스템 구축 사례가 있을까?"

### 4. 결과 확인

웹 UI에서 프로젝트 리스트가 테이블로 표시됩니다.

---

## 📝 참고 사항

### MCP 서버는 여전히 사용 가능

MCP 서버 (`mcp_server.py`)는 Cursor나 Claude Desktop과 연동할 때 사용할 수 있습니다:

```bash
# MCP 서버 실행 (Cursor/Claude Desktop용)
python mcp_server.py
```

### 공통 함수 사용

FastAPI와 MCP 서버 모두 `src/mcp_tools.py`의 공통 함수를 사용하므로:
- 동일한 로직 보장
- 코드 일관성 유지
- 버그 수정 시 한 곳만 수정하면 됨

---

## ✅ 완료

웹 UI에서 프롬프트를 입력하면 MCP 서버의 도구 함수가 호출되는 구조로 변경 완료되었습니다!
