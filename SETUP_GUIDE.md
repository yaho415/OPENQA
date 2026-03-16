# OpenQA+ 환경 구성 가이드

> **목적**: 다른 PC에서 동일한 OpenQA+ 개발 환경을 재현하기 위한 단계별 설치 및 설정 가이드
> **작성 기준일**: 2026년 2월

---

## 📅 2월 작업 데일리 요약

### 2/13 (목) — 프로젝트 초기 구성 및 백엔드 개발
| 시간대 | 작업 내용 |
|--------|-----------|
| 13:59 | 프로젝트 폴더 구조 생성 (`src/`, `server/`, `scripts/`, `__init__.py` 파일들) |
| 14:04 | 백엔드 핵심 모듈 개발: `case.py`(데이터 모델), `db.py`(DB 연결), `schema.sql`(테이블 스키마), `keyword_extractor.py`(TF-IDF 키워드 추출) |
| 14:08 | `.env` 환경변수 파일 생성 (DB 접속 정보, Ollama URL 등) |
| 14:20~14:26 | 웹 프론트엔드 초기 구성: React + Vite + TypeScript 프로젝트 생성, `npm install` 실행 |
| 16:25 | 벡터 임베딩 모듈(`vector_embedder.py`), 추천 엔진(`case_recommender.py`), 임베딩 생성 스크립트(`generate_embeddings.py`) 개발 |
| 16:25 | 성능 최적화 적용: `httpx.AsyncClient` 연결 재사용, LRU 캐시, 모델 워밍업 |

### 2/19 (수) — Git 저장소 초기화 및 GitHub 연동
| 시간대 | 작업 내용 |
|--------|-----------|
| 11:01 | `.gitignore` 생성, `git init`, 최초 커밋 수행 |
| 11:01 | GitHub 원격 저장소 연동 시도 (GCM 인증 이슈 해결) |

### 2/24 (월) — 대화형 Copilot UI 전환 및 기능 고도화
| 시간대 | 작업 내용 |
|--------|-----------|
| 14:32 | `server/app.py` 대폭 리팩토링: Qwen LLM 연동, 대화형 `/api/chat` 엔드포인트 추가, Python 측 의도 감지(Intent Detection), Qwen 대화 + 프로젝트 검색 병렬 실행 구현 |
| 14:41 | `App.css` 리디자인: 대화형 Copilot UI 스타일 적용 (채팅 인터페이스, 메시지 버블, 테이블 결과 표시) |
| 14:44 | `index.css` 수정: 전체 레이아웃 및 색상 테마 조정 |
| 14:46 | `logo.svg` 생성: 파란 원 + 흰색 "Q+" 로고 디자인 |
| 14:58 | `App.tsx` 완성: 대화형 UI 컴포넌트, 샘플 프롬프트, 새대화 버튼, 프로젝트 개요 접두사 제거 처리 |

### 2/25 (화) — 세부 UI 수정
| 시간대 | 작업 내용 |
|--------|-----------|
| - | 프롬프트 placeholder 텍스트 위치 확인 등 UI 미세 조정 |

---

## 🔧 단계별 환경 구성 가이드

### STEP 1. Python 설치
```
버전: Python 3.10 이상 권장 (3.11, 3.12도 가능)
다운로드: https://www.python.org/downloads/
```

**목적**: 백엔드 서버(FastAPI)와 모든 핵심 로직(임베딩, 추천 엔진, 키워드 추출)이 Python으로 작성되어 있음

**선택 이유**: 
- AI/ML 생태계가 가장 풍부한 언어
- FastAPI의 높은 성능(비동기 지원)과 자동 API 문서 생성
- 기존 MCP 프로젝트(TypeScript/Node.js)에서 Python으로 전환하여 유지보수 단일화

> ⚠️ 설치 시 "Add Python to PATH" 체크 필수

---

### STEP 2. Node.js 설치
```
버전: Node.js 18 LTS 이상
다운로드: https://nodejs.org/
```

**목적**: 웹 프론트엔드(React) 빌드 및 개발 서버 구동

**선택 이유**:
- React + Vite 조합으로 빠른 개발 서버(HMR) 제공
- TypeScript 지원으로 타입 안전성 확보

---

### STEP 3. PostgreSQL + pgvector 설치
```
PostgreSQL 버전: 15 이상 권장
pgvector 확장: https://github.com/pgvector/pgvector
```

**목적**: 프로젝트 사례 데이터 저장 및 벡터 유사도 검색(코사인 유사도)

**선택 이유**:
- `pgvector` 확장으로 벡터 임베딩을 DB에 직접 저장하고, SQL 한 줄로 유사도 검색 가능
- 별도의 벡터 DB(Pinecone, Weaviate 등) 없이 기존 RDB에서 벡터 검색을 통합 처리
- 1024차원 벡터를 `vector(1024)` 타입으로 네이티브 지원

**설치 후 설정**:
```sql
-- pgvector 확장 활성화
CREATE EXTENSION IF NOT EXISTS vector;

-- 데이터베이스 생성
CREATE DATABASE mcp_cases;
```

**스키마 적용**: `src/database/schema.sql` 파일이 서버 시작 시 자동으로 테이블을 생성합니다.

---

### STEP 4. Ollama 설치 (로컬 LLM 런타임)
```
다운로드: https://ollama.com/download
```

**목적**: 로컬 환경에서 AI 모델(임베딩, 대화)을 구동하기 위한 런타임

**선택 이유**:
- 클라우드 API 비용 없이 로컬에서 LLM 추론 가능
- GPU가 없어도 CPU에서 동작 (GPU 있으면 자동 가속)
- 간단한 명령어로 모델 다운로드/관리
- REST API(`http://localhost:11434`) 제공으로 언어에 무관하게 호출 가능

**설치 확인**:
```bash
ollama --version
```

---

### STEP 5. AI 모델 다운로드 (Ollama)

#### 5-1. BGE-M3 (텍스트 임베딩 모델)
```bash
ollama pull bge-m3
```

**목적**: 사용자 프롬프트와 프로젝트 데이터를 1024차원 벡터로 변환하여 의미 기반 유사도 검색 수행

**선택 이유**:
- 다국어(한국어 + 영어) 지원이 우수한 임베딩 모델
- 1024차원으로 충분한 표현력 제공
- Ollama에서 바로 사용 가능하여 별도 환경 구성 불필요
- Dense, Sparse, Multi-vector 검색을 모두 지원하는 범용 모델

#### 5-2. Qwen 2.5 (대화형 LLM)
```bash
ollama pull qwen2.5
```

**목적**: 사용자와의 일상 대화(인사, 질문 응답) 및 프로젝트 검색 결과에 대한 자연어 안내 메시지 생성

**선택 이유**:
- 한국어 대화 능력이 뛰어난 오픈소스 LLM
- 가벼운 모델 사이즈(7B)로 로컬 구동에 적합
- Ollama의 `/api/chat` 엔드포인트로 간편하게 호출

---

### STEP 6. 프로젝트 소스코드 클론
```bash
git clone https://github.com/<your-repo>/OPENQA.git
cd OPENQA
```

---

### STEP 7. Python 패키지 설치
```bash
pip install -r requirements.txt
```

**설치되는 주요 패키지**:

| 패키지 | 버전 | 용도 | 선택 이유 |
|--------|------|------|-----------|
| `fastapi` | 0.115.6 | REST API 서버 프레임워크 | 비동기 지원, 자동 OpenAPI 문서, Pydantic 통합 |
| `uvicorn` | 0.34.0 | ASGI 서버 (FastAPI 구동) | 고성능 비동기 HTTP 서버 |
| `psycopg2-binary` | 2.9.10 | PostgreSQL 드라이버 | Python 표준 PostgreSQL 어댑터 |
| `httpx` | 0.28.1 | 비동기 HTTP 클라이언트 | Ollama API 호출 시 연결 재사용(Keep-Alive) + async 지원 |
| `python-dotenv` | 1.0.1 | 환경변수 로드 (.env) | `.env` 파일에서 설정값 자동 로드 |
| `openai` | 1.58.1 | OpenAI 호환 클라이언트 | Qwen LLM 호출 시 선택적 사용 |
| `pydantic` | 2.10.4 | 데이터 검증/직렬화 | FastAPI 요청/응답 모델 정의 |

---

### STEP 8. 웹 프론트엔드 패키지 설치
```bash
cd web
npm install
cd ..
```

**설치되는 주요 패키지**:

| 패키지 | 용도 | 선택 이유 |
|--------|------|-----------|
| `react` / `react-dom` | UI 프레임워크 | 컴포넌트 기반 UI 개발, 풍부한 생태계 |
| `vite` | 빌드 도구 + 개발 서버 | Webpack 대비 10~100배 빠른 HMR, ES모듈 네이티브 지원 |
| `typescript` | 정적 타입 검사 | 코드 안전성 및 IDE 자동완성 강화 |
| `@vitejs/plugin-react` | Vite React 플러그인 | JSX 변환 및 Fast Refresh 지원 |

---

### STEP 9. 환경변수 설정 (.env)

프로젝트 루트(`C:\Users\OPENQA\`)에 `.env` 파일을 생성합니다:

```env
# PostgreSQL 데이터베이스 설정
DB_HOST=localhost
DB_PORT=5432
DB_NAME=mcp_cases
DB_USER=postgres
DB_PASSWORD=<your_password>

# Ollama 서버 URL (BGE-M3 임베딩 + Qwen 대화)
OLLAMA_URL=http://localhost:11434

# Qwen 모델 설정
QWEN_MODEL=qwen2.5

# 서버 포트
PORT=3001
```

---

### STEP 10. 데이터베이스 초기 데이터 및 임베딩 생성

```bash
# 사례 데이터가 DB에 이미 있는 경우, 벡터 임베딩 생성
python scripts/generate_embeddings.py
```

**목적**: 기존 프로젝트 사례 데이터에 대해 BGE-M3 벡터 임베딩을 생성하여 DB에 저장 (유사도 검색을 위한 필수 단계)

> ⚠️ Ollama가 구동 중이어야 합니다 (`ollama serve` 또는 Ollama 앱 실행)

---

### STEP 11. 서비스 구동

#### 터미널 1 — Ollama 서버 (이미 실행 중이면 생략)
```bash
ollama serve
```

#### 터미널 2 — 백엔드 API 서버 (FastAPI)
```bash
cd C:\Users\OPENQA
python server/app.py
```
→ `http://localhost:3001`에서 실행
→ API 문서: `http://localhost:3001/docs`

#### 터미널 3 — 웹 프론트엔드 (React + Vite)
```bash
cd C:\Users\OPENQA\web
npm run dev
```
→ `http://localhost:3000`에서 실행
→ API 요청은 Vite 프록시를 통해 `:3001`로 자동 전달

---

## 🏗️ 시스템 아키텍처 요약

```
사용자 (브라우저)
    │
    ▼ http://localhost:3000
┌────────────────────────────┐
│  React + Vite (프론트엔드)  │
│  - 대화형 Copilot UI       │
│  - 채팅 + 프로젝트 테이블   │
└────────────┬───────────────┘
             │ /api/* (Vite 프록시 → :3001)
             ▼
┌────────────────────────────┐
│  FastAPI (백엔드 서버)      │
│  - /api/chat (대화 + 추천)  │
│  - /api/recommend (추천)    │
│  - /api/health (헬스체크)   │
│  - Python 의도 감지         │
│  - TF-IDF 키워드 추출       │
└──────┬──────────┬──────────┘
       │          │
       ▼          ▼
┌──────────┐ ┌──────────────────┐
│PostgreSQL│ │  Ollama (local)   │
│+ pgvector│ │  ├ bge-m3 (임베딩)│
│          │ │  └ qwen2.5 (대화) │
└──────────┘ └──────────────────┘
```

---

## 📁 프로젝트 폴더 구조

```
OPENQA/
├── .env                          # 환경변수 (DB, Ollama 설정)
├── requirements.txt              # Python 패키지 의존성
├── server/
│   └── app.py                    # FastAPI 메인 서버 (Copilot API)
├── src/
│   ├── types/
│   │   └── case.py               # Case 데이터 모델 (dataclass)
│   ├── database/
│   │   ├── db.py                 # PostgreSQL 연결/CRUD/벡터검색
│   │   └── schema.sql            # DB 테이블 스키마
│   ├── keyword_extractor.py      # TF-IDF 키워드 추출기
│   ├── vector_embedder.py        # BGE-M3 벡터 임베딩 (httpx + LRU 캐시)
│   └── case_recommender.py       # 유사 프로젝트 추천 엔진
├── scripts/
│   └── generate_embeddings.py    # 기존 데이터 임베딩 생성 스크립트
└── web/
    ├── package.json              # Node.js 의존성
    ├── vite.config.ts            # Vite 설정 (프록시 포함)
    ├── index.html                # 진입 HTML
    ├── public/
    │   └── logo.svg              # Q+ 로고
    └── src/
        ├── main.tsx              # React 진입점
        ├── App.tsx               # 메인 컴포넌트 (대화형 UI)
        ├── App.css               # 스타일시트
        └── index.css             # 글로벌 스타일
```

---

## ⚡ 성능 최적화 포인트

| 최적화 | 적용 위치 | 효과 |
|--------|-----------|------|
| `httpx.AsyncClient` 연결 재사용 | `vector_embedder.py` | TCP 재연결 비용 제거, Keep-Alive |
| LRU 캐시 (200개) | `vector_embedder.py` | 동일 프롬프트 재호출 방지 (0.01초 → 즉시) |
| 모델 워밍업 | `server/app.py` lifespan | 첫 요청 지연 제거 (서버 시작 시 모델 로딩) |
| 병렬 실행 (`asyncio.gather`) | `server/app.py` /api/chat | Qwen 대화 + 프로젝트 검색 동시 수행 |
| DB 커넥션 풀 (1~20) | `db.py` SimpleConnectionPool | DB 연결 재사용으로 오버헤드 감소 |

---

## 🔑 핵심 기술 선택 사유 요약

| 기술 | 역할 | 선택 사유 |
|------|------|-----------|
| **FastAPI** | 백엔드 API | 비동기 네이티브, 자동 Swagger 문서, Pydantic 통합 |
| **PostgreSQL + pgvector** | 데이터 저장 + 벡터 검색 | 별도 벡터 DB 없이 RDB에서 임베딩 검색 통합 |
| **Ollama** | 로컬 LLM 런타임 | 무료, 로컬 구동, GPU/CPU 자동 선택, REST API 제공 |
| **BGE-M3** | 텍스트 → 벡터 임베딩 | 다국어(한/영) 우수, 1024차원, Dense+Sparse 통합 |
| **Qwen 2.5** | 대화형 LLM | 한국어 성능 우수, 7B 사이즈 로컬 적합, 오픈소스 |
| **TF-IDF** | 키워드 추출 | LLM 호출 없이 빠른 키워드 추출 (벡터 검색 보완용) |
| **React + Vite** | 웹 프론트엔드 | 빠른 HMR, TypeScript 지원, 컴포넌트 기반 UI |
| **httpx** | 비동기 HTTP | `requests` 대비 async 네이티브 + 연결 풀링 |

---

## 🛠️ 트러블슈팅 기록

| 문제 | 원인 | 해결 방법 |
|------|------|-----------|
| DB 연결 실패 (`fe_sendauth: no password supplied`) | `.env`에 DB 비밀번호 미설정 | `.env`에 `DB_PASSWORD` 추가 |
| `UnicodeEncodeError: cp949` | Windows 기본 인코딩이 cp949 | `sys.stdout.reconfigure(encoding="utf-8")` 추가 |
| 첫 요청 5~7초 소요 | Ollama 모델이 메모리에 미로딩 | 서버 시작 시 워밍업 호출 추가 |
| Git Push 403 에러 | GCM(Git Credential Manager) 캐시된 잘못된 인증 | `git -c credential.helper= push` 로 GCM 우회 |
| 프로젝트 추천 미동작 | Qwen이 `[SEARCH_PROJECTS]` 태그를 안정적으로 미생성 | Python 측 키워드 기반 의도 감지로 전환 |
| 포트 3000 충돌 | 이전 MCP 웹서버가 점유 | 기존 프로세스 종료 후 재시작 |
