# OpenQA+ MCP 서버 사용 가이드

> **MCP(Model Context Protocol) 서버로 전환 완료**  
> Qwen 2.5 통합 및 AI 클라이언트(Cursor, Claude Desktop) 연동 지원

---

## 📋 개요

OpenQA+ 프로젝트는 이제 **MCP 서버**로 구성되어 있습니다. 이는 AI 모델(Cursor, Claude Desktop 등)이 유사 프로젝트 추천 기능을 **도구(Tool)**로 사용할 수 있게 해줍니다.

### FastAPI vs MCP 서버

| 구분 | FastAPI REST API (`server/app.py`) | MCP 서버 (`mcp_server.py`) |
|------|-----------------------------------|---------------------------|
| **사용자** | 사람 (웹 브라우저) | AI 모델 (Cursor, Claude Desktop) |
| **통신 방식** | HTTP REST (JSON) | JSON-RPC over stdio/SSE |
| **호출 주체** | 사용자가 직접 입력 | AI가 필요할 때 자동 호출 |
| **인터페이스** | 웹 UI (채팅창) | Tool/Resource 정의 |
| **목적** | 사람에게 서비스 제공 | AI에게 "능력"을 제공 |

**현재 구성**:
- ✅ **MCP 서버** (`mcp_server.py`) - AI 클라이언트용 (메인)
- ✅ **FastAPI 서버** (`server/app.py`) - 웹 UI용 (유지)

---

## 🚀 MCP 서버 실행 방법

### 방법 1: stdio 모드 (Cursor/Claude Desktop 연동)

```bash
python mcp_server.py
```

이 모드는 Cursor나 Claude Desktop이 자동으로 MCP 서버를 호출할 때 사용됩니다.

### 방법 2: SSE 모드 (HTTP 서버)

```bash
python mcp_server.py --sse
```

HTTP 서버 모드로 실행되며, 외부에서 HTTP 요청으로 접근할 수 있습니다.

---

## 🔧 Cursor 연동 설정

### 1. 설정 파일 생성

`.cursor/mcp.json` 파일이 이미 생성되어 있습니다:

```json
{
  "mcpServers": {
    "openqa-recommender": {
      "command": "python",
      "args": [
        "C:\\Users\\OPENQA\\mcp_server.py"
      ],
      "env": {
        "DB_HOST": "localhost",
        "DB_PORT": "5432",
        "DB_NAME": "mcp_cases",
        "DB_USER": "postgres",
        "DB_PASSWORD": "admin123",
        "OLLAMA_URL": "http://localhost:11434",
        "QWEN_MODEL": "qwen2.5"
      }
    }
  }
}
```

### 2. Cursor 재시작

Cursor를 재시작하면 MCP 서버가 자동으로 연결됩니다.

### 3. 사용 방법

Cursor에서 다음과 같이 사용할 수 있습니다:

```
"금융권 차세대 시스템 구축 프로젝트를 찾아줘"
```

→ Cursor가 자동으로 `recommend_projects` 도구를 호출하여 결과를 반환합니다.

---

## 🛠️ 제공 도구 (Tools)

MCP 서버는 다음 6개의 도구를 제공합니다:

### 1. `recommend_projects` - 유사 프로젝트 추천

**벡터 유사도 기반 검색** (BGE-M3 + pgvector)

```python
recommend_projects(
    query: str,           # 검색할 프로젝트 설명
    max_results: int = 3  # 최대 결과 수 (기본값: 3)
)
```

**예시**:
- "금융권 차세대 시스템 구축"
- "공공기관 인사급여 시스템"
- "반도체 생산 품질 관리 시스템"

**반환값**: JSON 형태의 프로젝트 목록 (프로젝트명, 등급, 부서, 업종, 사업개요, 유사도 점수, 매칭 키워드)

---

### 2. `extract_keywords` - 키워드 추출

**TF-IDF 기반 키워드 추출**

```python
extract_keywords(
    text: str,            # 키워드를 추출할 텍스트
    max_keywords: int = 5 # 최대 키워드 수
)
```

---

### 3. `search_by_keyword` - 키워드 텍스트 검색

**정확한 텍스트 매칭 검색**

```python
search_by_keyword(
    keyword: str  # 검색할 키워드 (예: "ERP", "금융", "제조")
)
```

---

### 4. `get_project_stats` - 프로젝트 DB 통계

**데이터베이스 통계 정보 조회**

```python
get_project_stats()
```

**반환값**: 전체 프로젝트 수, 임베딩 상태, 업종/등급 분포

---

### 5. `get_project_detail` - 프로젝트 상세 조회

**프로젝트 ID로 상세 정보 조회**

```python
get_project_detail(
    project_id: str  # 프로젝트 고유 ID
)
```

---

### 6. `chat_with_qwen` - Qwen 2.5 대화형 AI ⭐

**Qwen 2.5 기반 대화형 AI 어시스턴트**

```python
chat_with_qwen(
    question: str,              # 질문 내용
    context: Optional[str] = None  # 추가 맥락 정보 (선택사항)
)
```

**예시 질문**:
- "ERP 시스템 구축 시 주의사항은?"
- "금융권 프로젝트의 특징은?"
- "프로젝트 기획 시 고려사항은?"

**특징**:
- Qwen 2.5 모델을 Ollama를 통해 호출
- 프로젝트 관련 전문 지식 제공
- `context` 파라미터에 프로젝트 검색 결과를 전달하면 더 정확한 답변 가능

**사용 시나리오**:
1. 사용자가 "금융권 차세대 시스템 구축 프로젝트를 찾아줘"라고 요청
2. Cursor가 `recommend_projects` 도구를 호출하여 결과 획득
3. 사용자가 "이 프로젝트들의 특징은?"이라고 추가 질문
4. Cursor가 `chat_with_qwen` 도구를 호출하여 검색 결과를 `context`로 전달
5. Qwen 2.5가 검색 결과를 바탕으로 전문적인 답변 생성

---

## 🔄 Qwen 2.5 통합 상세

### 통합 방식

1. **Ollama를 통한 호출**: Qwen 2.5 모델은 Ollama 서버(`http://localhost:11434`)를 통해 호출됩니다.
2. **비동기 처리**: `httpx.AsyncClient`를 사용하여 비동기적으로 호출합니다.
3. **연결 재사용**: 클라이언트를 싱글톤으로 관리하여 연결을 재사용합니다.

### 환경 변수

`.env` 파일 또는 `.cursor/mcp.json`의 `env` 섹션에서 설정:

```env
OLLAMA_URL=http://localhost:11434
QWEN_MODEL=qwen2.5
```

### 사전 요구사항

1. **Ollama 설치**: https://ollama.com/download
2. **Qwen 2.5 모델 다운로드**:
   ```bash
   ollama pull qwen2.5
   ```
3. **Ollama 서버 실행**:
   ```bash
   ollama serve
   ```
   또는 Ollama 앱을 실행

---

## 📊 아키텍처

```
AI 클라이언트 (Cursor/Claude Desktop)
    │
    ▼ JSON-RPC (stdio/SSE)
┌────────────────────────────┐
│  MCP 서버 (mcp_server.py)   │
│  - recommend_projects      │
│  - chat_with_qwen          │
│  - extract_keywords        │
│  - search_by_keyword       │
│  - get_project_stats       │
│  - get_project_detail      │
└──────┬──────────┬──────────┘
       │          │
       ▼          ▼
┌──────────┐ ┌──────────────────┐
│PostgreSQL│ │  Ollama (local)   │
│+ pgvector│ │  ├ bge-m3         │
│          │ │  └ qwen2.5         │
└──────────┘ └──────────────────┘
```

---

## 🧪 테스트

### MCP 서버 직접 테스트

```bash
# stdio 모드로 실행
python mcp_server.py
```

### Cursor에서 테스트

1. Cursor 재시작
2. 채팅창에서 다음을 입력:
   ```
   금융권 차세대 시스템 구축 프로젝트를 찾아줘
   ```
3. Cursor가 자동으로 `recommend_projects` 도구를 호출하여 결과를 반환합니다.

---

## 🔍 문제 해결

### MCP 서버가 연결되지 않는 경우

1. **Python 경로 확인**: `.cursor/mcp.json`의 `command`와 `args`가 올바른지 확인
2. **환경 변수 확인**: `.env` 파일 또는 `mcp.json`의 `env` 섹션 확인
3. **의존성 설치**: `pip install -r requirements.txt`
4. **Cursor 재시작**: 설정 변경 후 Cursor를 재시작

### Qwen 2.5 호출 실패

1. **Ollama 실행 확인**: `ollama serve` 또는 Ollama 앱 실행
2. **모델 다운로드 확인**: `ollama list`로 `qwen2.5` 모델이 있는지 확인
3. **포트 확인**: `OLLAMA_URL`이 `http://localhost:11434`인지 확인

### 데이터베이스 연결 실패

1. **PostgreSQL 실행 확인**: PostgreSQL 서버가 실행 중인지 확인
2. **연결 정보 확인**: `.env` 파일의 DB 설정 확인
3. **pgvector 확장 확인**: `CREATE EXTENSION IF NOT EXISTS vector;` 실행

---

## 📝 요약

- ✅ **MCP 서버로 전환 완료**: AI 클라이언트가 도구로 사용 가능
- ✅ **Qwen 2.5 통합**: 대화형 AI 어시스턴트 기능 제공
- ✅ **6개 도구 제공**: 프로젝트 추천, 검색, 통계, 상세 조회, 키워드 추출, Qwen 대화
- ✅ **Cursor 연동 지원**: `.cursor/mcp.json` 설정으로 자동 연결
- ✅ **FastAPI 유지**: 웹 UI는 기존 FastAPI 서버 사용

**핵심 차이점**:
- **FastAPI**: 사람이 웹에서 직접 사용
- **MCP 서버**: AI가 자동으로 도구를 호출하여 사용
