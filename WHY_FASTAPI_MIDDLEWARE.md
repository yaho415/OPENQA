# FastAPI를 거치는 이유와 대안

> **질문**: 사용자 프롬프트에서 바로 MCP 서버를 호출하지 않고 FastAPI를 거치는 이유는?

---

## 🔍 현재 구조 분석

### 현재 흐름
```
웹 UI (localhost:3000)
    ↓ HTTP POST /api/chat
FastAPI 서버 (localhost:3001)
    ↓ MCP 도구 함수 직접 호출
공통 도구 함수 (src/mcp_tools.py)
    ↓
핵심 로직 (BGE-M3 + pgvector)
```

---

## ✅ FastAPI를 거치는 이유

### 1. **Qwen 2.5 Tool Calling 통합**

FastAPI가 Qwen 2.5와의 대화형 인터랙션을 처리합니다:

```python
# server/app.py
async def chat_with_qwen_tool_calling(history, user_message):
    # 1. Qwen 2.5에게 사용자 메시지 + 도구 정의 전달
    # 2. Qwen이 tool_calls 반환 → 도구 자동 실행
    # 3. 도구 결과를 Qwen에 재전달 → 최종 응답 생성
```

**장점**:
- Qwen 2.5가 사용자 의도를 자동으로 판단하여 도구를 호출
- 자연스러운 대화형 인터랙션
- 일반 대화와 프로젝트 검색을 자동으로 구분

---

### 2. **의도 감지 Fallback**

Qwen이 도구를 호출하지 않았을 때 Python 기반 의도 감지:

```python
# Fallback: Qwen이 도구를 안 쓴 경우 Python 의도 감지
if recommendations is None and detect_project_intent(req.message):
    recommendations = await execute_recommend_projects(req.message, 3)
```

**장점**:
- Qwen이 실패하거나 도구를 호출하지 않아도 프로젝트 검색 가능
- 안정성 향상

---

### 3. **CORS 처리**

웹 브라우저의 CORS 정책을 처리:

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

**장점**:
- 브라우저에서 다른 도메인으로 요청 시 CORS 에러 방지
- 웹 UI와 API 서버가 다른 포트여도 문제없음

---

### 4. **에러 핸들링 및 로깅**

통합된 에러 처리:

```python
try:
    # Qwen 호출
except httpx.HTTPError:
    raise HTTPException(status_code=503, detail="Qwen 모델 서버에 연결할 수 없습니다...")
except Exception as e:
    raise HTTPException(status_code=500, detail=f"응답 생성 중 오류: {str(e)}")
```

**장점**:
- 일관된 에러 응답 형식
- 디버깅을 위한 로깅
- 사용자 친화적인 에러 메시지

---

### 5. **대화 히스토리 관리**

대화 컨텍스트 유지:

```python
history_dicts = [{"role": m.role, "content": m.content} for m in req.history]
messages.extend(recent_history)  # 최근 10개 메시지만 유지
```

**장점**:
- 이전 대화 맥락 유지
- 연속적인 대화 가능

---

### 6. **응답 포맷 통일**

웹 UI에 맞는 응답 형식:

```python
return {
    "success": True,
    "message": assistant_message,      # Qwen 응답
    "recommendations": recommendations, # 프로젝트 리스트
    "timing": round(total_elapsed, 2),  # 성능 측정
}
```

**장점**:
- 웹 UI에서 일관된 데이터 구조로 처리 가능
- 추가 메타데이터 (timing 등) 제공

---

## 🔄 대안: 웹 UI에서 직접 MCP 서버 호출

### 옵션 1: MCP 서버를 SSE 모드로 실행

MCP 서버를 HTTP 서버로 실행하고 웹 UI에서 직접 호출:

```bash
# MCP 서버를 SSE 모드로 실행
python mcp_server.py --sse
# → http://localhost:8000 에서 실행
```

**웹 UI에서 호출**:
```typescript
// web/src/App.tsx
const response = await fetch('http://localhost:8000/sse', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    jsonrpc: "2.0",
    id: 1,
    method: "tools/call",
    params: {
      name: "recommend_projects",
      arguments: { query: prompt, max_results: 3 }
    }
  })
});
```

**장점**:
- ✅ FastAPI 없이 직접 MCP 서버 호출
- ✅ 구조 단순화

**단점**:
- ❌ Qwen 2.5 Tool Calling 기능 사용 불가
- ❌ 의도 감지 fallback 없음
- ❌ 대화 히스토리 관리 어려움
- ❌ CORS 설정 필요 (MCP 서버에 추가)
- ❌ 에러 핸들링을 웹 UI에서 직접 처리해야 함

---

### 옵션 2: FastAPI 제거하고 MCP 서버만 사용

**구조**:
```
웹 UI → MCP 서버 (SSE 모드) → 도구 함수
```

**필요한 작업**:
1. MCP 서버에 CORS 미들웨어 추가
2. Qwen 2.5 통합을 MCP 서버로 이동
3. 웹 UI에서 MCP JSON-RPC 프로토콜 직접 처리

**장점**:
- ✅ 단일 서버로 구성 단순화
- ✅ MCP 프로토콜 직접 사용

**단점**:
- ❌ Qwen 2.5 Tool Calling 구현 복잡
- ❌ 웹 UI에서 JSON-RPC 프로토콜 직접 처리 필요
- ❌ 기존 FastAPI 기능들 재구현 필요

---

## 📊 비교표

| 항목 | 현재 (FastAPI 거침) | 직접 MCP 호출 |
|------|-------------------|--------------|
| **Qwen 2.5 Tool Calling** | ✅ 자동 도구 호출 | ❌ 수동 호출 |
| **의도 감지 Fallback** | ✅ Python 기반 | ❌ 없음 |
| **대화 히스토리** | ✅ 자동 관리 | ⚠️ 수동 관리 |
| **CORS 처리** | ✅ 자동 | ⚠️ MCP 서버에 추가 필요 |
| **에러 핸들링** | ✅ 통합 처리 | ⚠️ 웹 UI에서 처리 |
| **응답 포맷** | ✅ 웹 UI 최적화 | ⚠️ MCP 프로토콜 형식 |
| **구조 복잡도** | ⚠️ 중간 | ✅ 단순 |
| **유지보수** | ✅ 쉬움 | ⚠️ 어려움 |

---

## 🎯 권장 사항

### 현재 구조 유지 (권장) ✅

**이유**:
1. **Qwen 2.5 Tool Calling**: 사용자 의도를 자동으로 판단하여 도구를 호출하는 기능이 중요
2. **안정성**: Fallback 메커니즘이 있어 Qwen 실패 시에도 동작
3. **사용자 경험**: 자연스러운 대화형 인터랙션
4. **유지보수**: 기능이 분리되어 있어 수정이 쉬움

### 직접 MCP 호출로 변경 (선택적)

**언제 유용한가**:
- Qwen 2.5가 필요 없고 단순히 프로젝트 검색만 필요한 경우
- 구조를 최대한 단순화하고 싶은 경우
- MCP 프로토콜을 직접 사용해야 하는 경우

---

## 💡 결론

**FastAPI를 거치는 이유**:
1. ✅ **Qwen 2.5 Tool Calling**: 자동 의도 판단 및 도구 호출
2. ✅ **Fallback 메커니즘**: 안정성 향상
3. ✅ **CORS 처리**: 브라우저 호환성
4. ✅ **에러 핸들링**: 통합된 에러 처리
5. ✅ **대화 히스토리**: 컨텍스트 유지
6. ✅ **응답 포맷**: 웹 UI 최적화

**현재 구조가 더 나은 이유**:
- 사용자 경험이 더 좋음 (자동 의도 판단)
- 안정성이 높음 (Fallback)
- 유지보수가 쉬움 (기능 분리)

**직접 MCP 호출로 변경하려면**:
- Qwen 2.5 Tool Calling 기능을 포기해야 함
- 웹 UI에서 MCP JSON-RPC 프로토콜 직접 처리 필요
- CORS, 에러 핸들링 등을 별도로 구현 필요

---

## 🔧 만약 직접 MCP 호출로 변경한다면?

원하시면 웹 UI에서 직접 MCP 서버를 호출하도록 변경할 수 있습니다. 
다만 Qwen 2.5 Tool Calling 기능은 사용할 수 없게 됩니다.

변경하시겠습니까?
