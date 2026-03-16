# 프로세스 흐름 분석 및 검증

> 사용자가 설명한 프로세스와 실제 구현 코드를 비교 분석

---

## 📋 사용자가 설명한 프로세스

1. **Copilot 창에 사용자가 프롬프트를 입력한다.**
   (예: "금융사업의 ERP 원가 시스템을 구축하려고 해. 유사한 프로젝트를 알려줘.")

2. **Copilot에 있는 qwen2.5가 키워드를 추출하여 MCP 서버를 호출한다.**

3. **MCP 서버가 유사 프로젝트를 추천하는 Tool을 호출한다.**

4. **bge-m3가 프롬프트에서 추출된 키워드를 임베딩한다.**

5. **임베딩한 결과와 기존에 pgvector의 확장을 통해 임베딩되어있는 cases 테이블의 벡터 컬럼을 비교해서 유사도가 가장 높은 프로젝트를 찾는다.**

6. **선정된 프로젝트 리스트를 Copilot에 전달하여 응답창에 보여준다.**

---

## 🔍 실제 구현 코드 분석

### 현재 시스템 구조

시스템은 **두 가지 경로**로 동작합니다:

#### 경로 1: 웹 UI → FastAPI 서버 (현재 웹에서 사용 중)
```
웹 UI (React) → FastAPI (/api/chat) → Qwen 2.5 + Python 의도 감지 → 프로젝트 검색
```

#### 경로 2: AI 클라이언트 → MCP 서버 (Cursor/Claude Desktop용)
```
AI 클라이언트 → MCP 서버 (mcp_server.py) → recommend_projects 도구 → 프로젝트 검색
```

---

## ✅ 프로세스 검증 결과

### 사용자 설명 vs 실제 구현 비교

| 단계 | 사용자 설명 | 실제 구현 | 일치 여부 | 비고 |
|------|------------|----------|----------|------|
| **1** | Copilot 창에 프롬프트 입력 | ✅ 웹 UI (`App.tsx`) 또는 Cursor에서 입력 | ✅ **일치** | - |
| **2** | Qwen 2.5가 키워드 추출하여 MCP 서버 호출 | ⚠️ **부분 일치** | ⚠️ **차이 있음** | 아래 상세 설명 |
| **3** | MCP 서버가 추천 Tool 호출 | ✅ `recommend_projects` 도구 호출 | ✅ **일치** | - |
| **4** | bge-m3가 키워드를 임베딩 | ⚠️ **부분 일치** | ⚠️ **차이 있음** | 아래 상세 설명 |
| **5** | pgvector로 유사도 비교 | ✅ `search_similar_cases_by_vector` | ✅ **일치** | - |
| **6** | 프로젝트 리스트를 Copilot에 전달 | ✅ JSON 응답 반환 | ✅ **일치** | - |

---

## 🔎 상세 분석

### ⚠️ 차이점 1: 키워드 추출 시점과 주체

**사용자 설명**:
> "Copilot에 있는 qwen2.5가 키워드를 추출하여 MCP 서버를 호출한다."

**실제 구현** (`mcp_server.py:105-108`):
```python
@mcp.tool()
async def recommend_projects(query: str, max_results: int = 3) -> str:
    keywords = _extractor.extract_keywords(query, 10)  # TF-IDF로 키워드 추출
    recommendations = await _recommender.recommend_similar_cases(
        query, max_results, keywords
    )
```

**실제 동작**:
- ❌ Qwen 2.5가 키워드를 추출하지 **않습니다**
- ✅ MCP 서버 내부에서 **TF-IDF 기반 키워드 추출기** (`KeywordExtractor`)가 키워드를 추출합니다
- ✅ 키워드는 **매칭 키워드 표시용**으로만 사용되며, 임베딩에는 사용되지 않습니다

**수정 제안**:
```
2. MCP 서버가 recommend_projects 도구를 호출받으면, 
   내부에서 TF-IDF 기반 키워드 추출기를 사용하여 키워드를 추출한다.
```

---

### ⚠️ 차이점 2: 임베딩 대상

**사용자 설명**:
> "bge-m3가 프롬프트에서 추출된 키워드를 임베딩한다."

**실제 구현** (`case_recommender.py:104-105`):
```python
# 1. 사용자 프롬프트를 벡터로 변환 (async)
query_embedding = await self.embedder.embed(user_prompt)  # 전체 프롬프트를 임베딩
```

**실제 동작**:
- ❌ 추출된 키워드를 임베딩하지 **않습니다**
- ✅ **전체 사용자 프롬프트**를 BGE-M3로 임베딩합니다
- ✅ 키워드는 유사도 계산 후 **매칭 키워드 표시**에만 사용됩니다

**수정 제안**:
```
4. bge-m3가 사용자 프롬프트 전체를 1024차원 벡터로 임베딩한다.
   (키워드가 아닌 전체 프롬프트를 임베딩)
```

---

## 📊 실제 프로세스 흐름 (정확한 버전)

### MCP 서버 경로 (Cursor/Claude Desktop)

```
1. 사용자가 Cursor/Copilot에서 프롬프트 입력
   "금융사업의 ERP 원가 시스템을 구축하려고 해. 유사한 프로젝트를 알려줘."

2. AI 클라이언트(Cursor)가 MCP 서버의 recommend_projects 도구를 호출
   → mcp_server.py의 @mcp.tool() recommend_projects 함수 실행

3. MCP 서버 내부 처리:
   a) TF-IDF 기반 키워드 추출 (KeywordExtractor)
      → 키워드: ["금융", "ERP", "원가", "시스템", "구축"]
      → 용도: 매칭 키워드 표시용 (임베딩에는 사용 안 함)
   
   b) CaseRecommender.recommend_similar_cases() 호출

4. CaseRecommender 내부:
   a) 전체 프롬프트를 BGE-M3로 임베딩
      → VectorEmbedder.embed(user_prompt)
      → Ollama BGE-M3 API 호출
      → 1024차원 벡터 반환
   
   b) PostgreSQL + pgvector로 유사도 검색
      → db.search_similar_cases_by_vector(query_embedding, max_results)
      → SQL: "ORDER BY embedding <=> %s::vector LIMIT %s"
      → 코사인 유사도 계산 (1 - (embedding <=> query) / 2.0)
   
   c) 매칭 키워드 찾기
      → 추출된 키워드와 프로젝트 데이터 비교
      → matched_keywords 배열 생성

5. 결과 포맷팅 및 반환
   → JSON 형태로 프로젝트 목록 반환
   → 각 프로젝트: id, projectName, grade, department, industry, 
                  businessOverview, score, matchedKeywords

6. AI 클라이언트가 결과를 사용자에게 표시
   → Cursor/Copilot 응답창에 프로젝트 리스트 표시
```

---

### 웹 UI 경로 (현재 웹에서 사용 중)

```
1. 사용자가 웹 UI에서 프롬프트 입력
   "금융사업의 ERP 원가 시스템을 구축하려고 해. 유사한 프로젝트를 알려줘."

2. React 앱이 FastAPI 서버로 POST /api/chat 요청
   → server/app.py의 chat() 함수 실행

3. FastAPI 서버 처리:
   a) Python 측 의도 감지 (detect_project_intent)
      → 정규식 패턴 매칭으로 프로젝트 추천 의도 판단
   
   b) 병렬 실행 (asyncio.gather):
      - Qwen 2.5 대화 호출 (chat_with_qwen)
      - 프로젝트 검색 (search_similar_projects)
        → CaseRecommender.recommend_similar_cases() 호출
        → (MCP 서버와 동일한 로직)

4. CaseRecommender 내부 (MCP 서버와 동일):
   a) 전체 프롬프트를 BGE-M3로 임베딩
   b) pgvector로 유사도 검색
   c) 매칭 키워드 찾기

5. FastAPI가 결과 반환
   → { message: Qwen 응답, recommendations: 프로젝트 리스트 }

6. 웹 UI가 결과 표시
   → 채팅 메시지 + 프로젝트 테이블 렌더링
```

---

## 🎯 핵심 차이점 요약

| 항목 | 사용자 설명 | 실제 구현 |
|------|------------|----------|
| **키워드 추출 주체** | Qwen 2.5 | TF-IDF 기반 KeywordExtractor |
| **키워드 추출 시점** | MCP 서버 호출 전 | MCP 서버 내부 (도구 실행 시) |
| **임베딩 대상** | 추출된 키워드 | 전체 사용자 프롬프트 |
| **키워드 용도** | 임베딩에 사용 | 매칭 키워드 표시용만 |

---

## ✅ 수정된 정확한 프로세스

### MCP 서버 경로 (정확한 버전)

```
1. Copilot 창에 사용자가 프롬프트를 입력한다.
   (예: "금융사업의 ERP 원가 시스템을 구축하려고 해. 유사한 프로젝트를 알려줘.")

2. AI 클라이언트(Cursor/Copilot)가 MCP 서버의 recommend_projects 도구를 호출한다.
   (Qwen 2.5가 키워드를 추출하는 것이 아니라, AI 클라이언트가 직접 도구를 호출)

3. MCP 서버가 recommend_projects 도구를 실행한다.
   - 내부에서 TF-IDF 기반 키워드 추출기로 키워드를 추출한다.
   - (키워드는 매칭 키워드 표시용이며, 임베딩에는 사용되지 않음)

4. CaseRecommender가 전체 사용자 프롬프트를 BGE-M3로 임베딩한다.
   (추출된 키워드가 아닌 전체 프롬프트를 임베딩)

5. 임베딩한 결과와 pgvector의 cases 테이블 벡터 컬럼을 비교하여 
   코사인 유사도가 가장 높은 프로젝트를 찾는다.
   (SQL: "ORDER BY embedding <=> %s::vector LIMIT %s")

6. 선정된 프로젝트 리스트를 JSON 형태로 반환하고, 
   AI 클라이언트가 Copilot 응답창에 보여준다.
```

---

## 🔧 개선 제안

현재 구현이 사용자가 설명한 프로세스와 약간 다릅니다. 다음 중 하나를 선택할 수 있습니다:

### 옵션 1: 현재 구현 유지 (권장)
- ✅ 전체 프롬프트를 임베딩하는 것이 더 정확한 의미 검색 가능
- ✅ 키워드 추출은 매칭 키워드 표시용으로만 사용 (효율적)

### 옵션 2: 사용자 설명대로 수정
- Qwen 2.5가 키워드를 추출하도록 변경
- 추출된 키워드를 BGE-M3로 임베딩
- (하지만 이는 전체 프롬프트 임베딩보다 정확도가 낮을 수 있음)

---

## 📝 결론

**사용자가 설명한 프로세스와 실제 구현의 차이**:

1. ✅ **대부분 일치**: 전체 흐름은 정확합니다
2. ⚠️ **키워드 추출**: Qwen 2.5가 아닌 TF-IDF 기반 추출기 사용
3. ⚠️ **임베딩 대상**: 키워드가 아닌 전체 프롬프트를 임베딩

**실제 동작은 더 효율적이고 정확합니다**:
- 전체 프롬프트 임베딩이 의미 검색에 더 유리
- 키워드는 매칭 표시용으로만 사용하여 불필요한 처리 제거
