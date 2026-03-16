"""
FastAPI REST 서버 - OpenQA+ Copilot 대화형 서비스

아키텍처:
  - Qwen 2.5 LLM (Ollama) + Tool Calling (Function Calling)
  - MCP 도구와 동일한 기능을 Qwen의 도구로 등록
  - Qwen이 사용자 의도를 판단하여 자동으로 도구 호출
  - Python 측 의도 감지를 fallback으로 유지

흐름:
  사용자 → Qwen 2.5 (도구 정의 포함) → 도구 호출 필요? 
    → Yes: 도구 실행 → 결과를 Qwen에 전달 → 최종 응답
    → No:  직접 응답 (일반 대화)
"""

import asyncio
import json
import os
import re
import sys
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import List, Optional

import httpx

# 프로젝트 루트를 sys.path에 추가
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv

from src.case_recommender import CaseRecommender
from src.keyword_extractor import KeywordExtractor
from src.vector_embedder import get_vector_embedder
from src.database.db import get_database
from src.mcp_tools import recommend_projects_tool, update_projects_from_excel  # MCP 도구 함수 사용

load_dotenv()

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
QWEN_MODEL = os.getenv("QWEN_MODEL", "qwen2.5")


# ──────────────────────────────────────────────────────────
# Qwen 2.5 Tool Calling 도구 정의
# ──────────────────────────────────────────────────────────
QWEN_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "recommend_projects",
            "description": (
                "사용자의 요구사항과 유사한 프로젝트를 벡터 유사도 기반으로 검색하고 추천합니다. "
                "프로젝트를 찾거나, 사례를 추천받거나, 시스템 구축 사례를 검색하는 요청에 사용합니다. "
                "예: '금융권 차세대 시스템 구축 사례', '공공기관 인사급여 시스템 프로젝트'"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "검색할 프로젝트 설명 또는 키워드",
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "반환할 최대 결과 수 (기본값: 5)",
                        "default": 5,
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_projects_from_excel",
            "description": (
                "Excel 파일(xlsx)을 읽어서 프로젝트 현황(project 테이블)을 업데이트합니다. "
                "project_code 기준으로 변경된 데이터가 있으면 업데이트하고, updated_at을 현재 시간으로 변경합니다. "
                "업데이트된 데이터는 BGE-M3를 통해 임베딩을 생성하여 벡터값도 업데이트합니다. "
                "Excel 파일에는 project_code, project_name 컬럼이 필수입니다."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "업데이트할 Excel 파일의 경로 (절대 경로 또는 상대 경로)",
                    },
                },
                "required": ["file_path"],
            },
        },
    },
]


# ──────────────────────────────────────────────────────────
# Python 측 의도 감지 (Qwen Fallback)
# ──────────────────────────────────────────────────────────
PROJECT_INTENT_PATTERNS = [
    r"프로젝트.*찾아", r"프로젝트.*추천", r"프로젝트.*검색",
    r"프로젝트.*알려", r"프로젝트.*있[어을나]",
    r"사례.*찾아", r"사례.*추천", r"사례.*검색", r"사례.*알려",
    r"사례.*있[어을나]",
    r"유사.*프로젝트", r"유사.*사례", r"비슷한.*프로젝트", r"비슷한.*사례",
    r"시스템.*구축", r"시스템.*개발", r"시스템.*도입",
    r"솔루션.*구축", r"솔루션.*도입",
    r"플랫폼.*구축", r"플랫폼.*개발",
    r"관련.*프로젝트", r"관련.*사례",
    r"업무.*사례", r"업종.*사례",
    r"구축.*사례", r"개발.*사례", r"도입.*사례",
    r"어떤.*프로젝트", r"어떤.*사례",
    r"찾아줘", r"추천해줘", r"추천.*해줘", r"검색.*해줘",
    r"ERP", r"SCM", r"CRM", r"MES", r"WMS", r"HR",
    r"고도화", r"차세대",
]


def detect_project_intent(message: str) -> bool:
    """사용자 메시지에서 프로젝트 추천 의도를 감지 (Python fallback)"""
    for pattern in PROJECT_INTENT_PATTERNS:
        if re.search(pattern, message, re.IGNORECASE):
            return True
    return False


# 파일 반영 의도 감지 패턴
FILE_REFLECTION_PATTERNS = [
    r"반영", r"적용", r"업데이트", r"처리", r"실행", r"진행",
    r"파일.*반영", r"파일.*적용", r"파일.*업데이트", r"파일.*처리",
    r"첨부.*반영", r"첨부.*적용", r"첨부.*업데이트", r"첨부.*처리",
    r"프로젝트.*현황.*반영", r"프로젝트.*현황.*적용",
]


def detect_file_reflection_intent(message: str) -> bool:
    """사용자 메시지에서 파일 반영 의도를 감지"""
    for pattern in FILE_REFLECTION_PATTERNS:
        if re.search(pattern, message, re.IGNORECASE):
            return True
    return False


# ──────────────────────────────────────────────────────────
# Qwen 2.5 클라이언트
# ──────────────────────────────────────────────────────────
_qwen_client: Optional[httpx.AsyncClient] = None


def get_qwen_client() -> httpx.AsyncClient:
    global _qwen_client
    if _qwen_client is None:
        _qwen_client = httpx.AsyncClient(
            base_url=OLLAMA_URL,
            timeout=httpx.Timeout(120.0, connect=10.0),
        )
    return _qwen_client


SYSTEM_PROMPT = """너는 OpenQA+ Copilot이야. 사용자를 도와주는 친절한 AI 어시스턴트야.

역할:
- 반드시 한국어로만 답변해. 절대로 중국어(中文)나 영어로 답변하지 마.
- 답변은 간결하고 친절하게 해줘.
- 사용자가 프로젝트나 사례를 찾으면 반드시 recommend_projects 도구를 사용해.
- 도구 실행 결과가 있으면 의견을 말하지말고, "결과를 보여드리겠습니다."한 줄만 답변해.
- 절대로 프로젝트 목록을 텍스트로 나열하지 마.
- 프로젝트 목록은 시스템이 테이블로 자동 표시하므로 너는 안내 문구만 출력하면 돼.
- 인사, 질문, 잡담 등 일반 대화는 자유롭게 해줘.
"""


# ──────────────────────────────────────────────────────────
# 도구 실행 함수들 (MCP 도구와 동일한 로직)
# ──────────────────────────────────────────────────────────
case_recommender = CaseRecommender()
keyword_extractor = KeywordExtractor()


async def execute_recommend_projects(query: str, max_results: int = 5) -> list:
    """유사 프로젝트 검색 실행 (MCP 도구 함수 사용)"""
    result = await recommend_projects_tool(query, max_results)
    return result.get("recommendations", [])


async def execute_tool(name: str, arguments: dict) -> tuple:
    """
    도구 실행 및 결과 반환

    Returns:
        (tool_result_str, recommendations_for_frontend)
    """
    recommendations = None

    if name == "recommend_projects":
        query = arguments.get("query", "")
        max_results = arguments.get("max_results", 5)
        recommendations = await execute_recommend_projects(query, max_results)
        result_str = json.dumps(recommendations, ensure_ascii=False, indent=2)

    elif name == "update_projects_from_excel":
        file_path = arguments.get("file_path", "")
        result = await update_projects_from_excel(file_path)
        result_str = json.dumps(result, ensure_ascii=False, indent=2)

    else:
        result_str = f"알 수 없는 도구: {name}"

    return result_str, recommendations


# ──────────────────────────────────────────────────────────
# Qwen 2.5 Tool Calling 대화 루프
# ──────────────────────────────────────────────────────────
async def chat_with_qwen_tool_calling(
    history: List[dict], user_message: str
) -> tuple:
    """
    Qwen 2.5 Tool Calling 대화 루프

    Returns:
        (assistant_message: str, recommendations: list|None)
    """
    client = get_qwen_client()

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    recent_history = history[-10:] if len(history) > 10 else history
    messages.extend(recent_history)
    messages.append({"role": "user", "content": user_message})

    recommendations = None

    # ── 1단계: Qwen 호출 (도구 정의 포함) ──
    t1 = time.time()
    resp = await client.post(
        "/api/chat",
        json={
            "model": QWEN_MODEL,
            "messages": messages,
            "tools": QWEN_TOOLS,
            "stream": False,
            "options": {"temperature": 0.7, "num_predict": 1024},
        },
    )
    resp.raise_for_status()
    data = resp.json()
    assistant_msg = data.get("message", {})
    t1_elapsed = time.time() - t1
    print(f"[TIMING] Qwen 1차 호출 (Tool Calling): {t1_elapsed:.2f}초")

    # ── 2단계: Tool Call 처리 ──
    tool_calls = assistant_msg.get("tool_calls")

    if tool_calls:
        print(f"[TOOL] Qwen이 {len(tool_calls)}개 도구 호출을 요청했습니다")

        for tc in tool_calls:
            func = tc.get("function", {})
            func_name = func.get("name", "")
            func_args = func.get("arguments", {})

            if isinstance(func_args, str):
                try:
                    func_args = json.loads(func_args)
                except json.JSONDecodeError:
                    func_args = {"query": func_args}

            print(f"[TOOL] 실행: {func_name}({func_args})")

            t2 = time.time()
            tool_result, tool_recommendations = await execute_tool(func_name, func_args)
            t2_elapsed = time.time() - t2
            print(f"[TIMING] 도구 실행 ({func_name}): {t2_elapsed:.2f}초")

            if tool_recommendations is not None:
                recommendations = tool_recommendations

        # ── 3단계: 도구 결과를 Qwen에 전달하여 최종 응답 생성 ──
        messages.append(assistant_msg)
        messages.append({"role": "tool", "content": tool_result})

        t3 = time.time()
        resp2 = await client.post(
            "/api/chat",
            json={
                "model": QWEN_MODEL,
                "messages": messages,
                "stream": False,
                "options": {"temperature": 0.7, "num_predict": 512},
            },
        )
        resp2.raise_for_status()
        data2 = resp2.json()
        final_text = data2.get("message", {}).get("content", "")
        t3_elapsed = time.time() - t3
        print(f"[TIMING] Qwen 2차 호출 (최종 응답): {t3_elapsed:.2f}초")

        if not final_text:
            final_text = "요청하신 내용과 유사한 프로젝트를 찾아보았습니다. 아래 결과를 확인해주세요."

        return final_text, recommendations

    else:
        content = assistant_msg.get("content", "")
        return content, None


# ──────────────────────────────────────────────────────────
# Lifespan: 서버 시작/종료
# ──────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """서버 시작 시 모델 워밍업, 종료 시 리소스 정리"""
    embedder = get_vector_embedder()
    await embedder.warm_up()
    print("[READY] 서버 준비 완료 - BGE-M3 모델 워밍업 됨")
    print(f"[MODE] Qwen 2.5 Tool Calling + MCP 도구 연동")
    yield
    await embedder.close()
    global _qwen_client
    if _qwen_client:
        await _qwen_client.aclose()
    print("[SHUTDOWN] 리소스 정리 완료")


# ──────────────────────────────────────────────────────────
# FastAPI 앱 설정
# ──────────────────────────────────────────────────────────
app = FastAPI(
    title="OpenQA+ Copilot (MCP + Qwen 2.5 Tool Calling)",
    description="Qwen 2.5 Tool Calling 기반 대화형 AI + MCP 도구 연동 유사 프로젝트 추천",
    version="4.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ──────────────────────────────────────────────────────────
# 요청/응답 모델
# ──────────────────────────────────────────────────────────
class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    message: str
    history: List[ChatMessage] = []
    attached_file_path: Optional[str] = None


class RecommendRequest(BaseModel):
    prompt: str
    max_results: int = 5


# ──────────────────────────────────────────────────────────
# API 엔드포인트
# ──────────────────────────────────────────────────────────
@app.post("/api/chat")
async def chat(req: ChatRequest):
    """
    대화형 Copilot API - Qwen 2.5 Tool Calling + MCP 도구
    """
    # 메시지가 비어있고 파일도 첨부되지 않았으면 에러
    if (not req.message or not req.message.strip()) and not req.attached_file_path:
        raise HTTPException(status_code=400, detail="메시지를 입력하거나 파일을 첨부해주세요.")

    try:
        total_start = time.time()
        history_dicts = [{"role": m.role, "content": m.content} for m in req.history]

        # ── Qwen 2.5 Tool Calling 시도 ──
        try:
            assistant_message, recommendations = await chat_with_qwen_tool_calling(
                history_dicts, req.message
            )
            print(f"[TOOL-CALLING] Qwen 도구 호출 {'사용' if recommendations else '미사용'}")

        except httpx.HTTPError as e:
            print(f"[ERROR] Qwen 호출 실패: {e}")
            raise

        # ── 파일 반영 의도 감지 및 자동 처리 ──
        message_text = req.message.strip() if req.message else ""
        if req.attached_file_path and (not message_text or detect_file_reflection_intent(message_text)):
            print(f"[FILE-REFLECTION] 파일 반영 의도 감지 → 파일 경로: {req.attached_file_path}")
            
            file_path_obj = Path(req.attached_file_path)
            if not file_path_obj.is_absolute():
                file_path_obj = Path(os.path.abspath(req.attached_file_path))
            
            print(f"[FILE-REFLECTION] 파일 경로 확인: {file_path_obj} (존재: {file_path_obj.exists()})")
            
            if not file_path_obj.exists():
                print(f"[FILE-REFLECTION-ERROR] 파일을 찾을 수 없음: {file_path_obj}")
                assistant_message = f"❌ 파일을 찾을 수 없습니다: {file_path_obj}"
            else:
                try:
                    from src.mcp_tools import update_projects_from_excel
                    result = await update_projects_from_excel(str(file_path_obj))
                    
                    if result.get("success"):
                        updated_count = result.get("updatedCount", 0)
                        error_count = result.get("errorCount", 0)
                        timing = result.get("timingSeconds", 0)
                        
                        assistant_message = (
                            f"✅ 프로젝트 현황 파일이 성공적으로 반영되었습니다!\n\n"
                            f"- 업데이트된 프로젝트: {updated_count}개\n"
                            f"- 오류: {error_count}개\n"
                            f"- 소요 시간: {timing}초"
                        )
                        
                        if result.get("updatedIds"):
                            ids = result["updatedIds"][:10]
                            assistant_message += f"\n\n업데이트된 프로젝트 코드: {', '.join(ids)}"
                            if len(result["updatedIds"]) > 10:
                                assistant_message += f" 외 {len(result['updatedIds']) - 10}개"
                    else:
                        assistant_message = f"❌ 파일 반영 실패: {result.get('message', '알 수 없는 오류')}"
                        
                except Exception as e:
                    print(f"[ERROR] 파일 반영 처리 중 오류: {e}")
                    assistant_message = f"❌ 파일 반영 중 오류가 발생했습니다: {str(e)}"
        
        # ── Fallback: Qwen이 도구를 안 쓴 경우 Python 의도 감지 ──
        elif recommendations is None and detect_project_intent(req.message):
            print("[FALLBACK] Python 의도 감지 → 프로젝트 검색 실행")
            t_fb = time.time()
            recommendations = await execute_recommend_projects(req.message, 5)
            print(f"[TIMING] Fallback 검색: {time.time() - t_fb:.2f}초")

            if not assistant_message:
                assistant_message = "요청하신 내용과 유사한 프로젝트를 찾아보았습니다. 아래 결과를 확인해주세요."

        total_elapsed = time.time() - total_start
        print(f"[TIMING] === 전체 소요시간: {total_elapsed:.2f}초 ===")

        return {
            "success": True,
            "message": assistant_message,
            "recommendations": recommendations,
            "timing": round(total_elapsed, 2),
        }

    except httpx.HTTPError:
        raise HTTPException(
            status_code=503,
            detail="Qwen 모델 서버에 연결할 수 없습니다. Ollama가 실행 중인지 확인해주세요.",
        )
    except Exception as e:
        print(f"[ERROR] 채팅 오류: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"응답 생성 중 오류가 발생했습니다: {str(e)}",
        )


@app.post("/api/upload-file")
async def upload_file(file: UploadFile = File(...)):
    """파일 업로드 API - 임시 파일로 저장하고 경로 반환"""
    if not file.filename or not file.filename.endswith(('.xlsx', '.xls')):
        raise HTTPException(
            status_code=400,
            detail="지원하지 않는 파일 형식입니다. .xlsx 또는 .xls 파일만 지원합니다."
        )
    
    # temp 디렉토리 생성 (절대 경로 사용)
    temp_dir = os.path.abspath(os.path.join(os.getcwd(), 'temp'))
    os.makedirs(temp_dir, exist_ok=True)
    print(f"[UPLOAD] temp 디렉토리: {temp_dir} (존재: {os.path.exists(temp_dir)})")
    
    temp_file = None
    try:
        suffix = Path(file.filename).suffix
        contents = await file.read()
        print(f"[UPLOAD] 파일 내용 읽기 완료: {len(contents)} bytes")
        
        temp_file = os.path.join(temp_dir, f"upload_{int(time.time() * 1000)}{suffix}")
        print(f"[UPLOAD] 임시 파일 경로: {temp_file}")
        
        with open(temp_file, 'wb') as f:
            f.write(contents)
        
        print(f"[UPLOAD] 파일 저장 완료: {temp_file} (존재: {os.path.exists(temp_file)})")
        
        return {
            "success": True,
            "file_path": temp_file,
            "filename": file.filename,
        }
        
    except Exception as e:
        print(f"[UPLOAD-ERROR] 파일 업로드 실패: {str(e)}")
        if temp_file and os.path.exists(temp_file):
            try:
                os.unlink(temp_file)
            except:
                pass
        raise HTTPException(
            status_code=500,
            detail=f"파일 업로드 중 오류가 발생했습니다: {str(e)}"
        )


@app.post("/api/recommend")
async def recommend_projects_api(req: RecommendRequest):
    """유사 프로젝트 추천 API (기존 호환)"""
    if not req.prompt or not req.prompt.strip():
        raise HTTPException(status_code=400, detail="prompt는 필수 파라미터입니다.")

    try:
        total_start = time.time()
        result = await execute_recommend_projects(req.prompt, req.max_results)
        total_elapsed = time.time() - total_start
        print(f"[TIMING] 추천 API: {total_elapsed:.2f}초")

        keywords = keyword_extractor.extract_keywords(req.prompt, 10)

        return {
            "success": True,
            "prompt": req.prompt,
            "keywords": keywords,
            "recommendations": result,
            "total": len(result),
        }
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"프로젝트 추천 중 오류가 발생했습니다: {str(e)}",
        )


@app.post("/api/update-projects")
async def update_projects_api(file: UploadFile = File(...)):
    """Excel 파일 업로드를 통해 프로젝트 현황 업데이트 API"""
    if not file.filename.endswith(('.xlsx', '.xls')):
        raise HTTPException(
            status_code=400,
            detail="지원하지 않는 파일 형식입니다. .xlsx 또는 .xls 파일만 지원합니다."
        )
    
    import tempfile
    import shutil
    
    temp_file = None
    try:
        suffix = Path(file.filename).suffix
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            shutil.copyfileobj(file.file, tmp)
            temp_file = tmp.name
        
        result = await update_projects_from_excel(temp_file)
        return result
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"파일 처리 중 오류가 발생했습니다: {str(e)}"
        )
    finally:
        if temp_file and os.path.exists(temp_file):
            try:
                os.unlink(temp_file)
            except:
                pass


@app.get("/api/health")
async def health_check():
    """건강 체크 API"""
    db_status = "unknown"
    try:
        db = get_database()
        db.get_all_projects()
        db_status = "connected"
    except Exception:
        db_status = "disconnected"

    qwen_status = "unknown"
    try:
        client = get_qwen_client()
        resp = await client.get("/api/tags")
        resp.raise_for_status()

        models = resp.json().get("models", [])
        qwen_found = any(QWEN_MODEL in m.get("name", "") for m in models)
        qwen_status = "connected" if qwen_found else "connected (model not found)"
    except Exception:
        qwen_status = "disconnected"

    embedder = get_vector_embedder()

    return {
        "status": "ok",
        "mode": "Qwen 2.5 Tool Calling + MCP",
        "model": QWEN_MODEL,
        "database": db_status,
        "qwen": qwen_status,
        "embedding_cache": embedder.get_cache_stats(),
        "tools": [t["function"]["name"] for t in QWEN_TOOLS],
    }


# ──────────────────────────────────────────────────────────
# 서버 실행
# ──────────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn

    # Windows cp949 인코딩 문제 해결
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    port = int(os.getenv("PORT", "3001"))
    print(f"[START] http://localhost:{port}")
    print(f"[MODE] Qwen 2.5 Tool Calling + MCP 도구 연동")
    print(f"[MODEL] {QWEN_MODEL} via Ollama ({OLLAMA_URL})")
    print(f"[TOOLS] {', '.join(t['function']['name'] for t in QWEN_TOOLS)}")
    print(f"[DOCS] http://localhost:{port}/docs")

    uvicorn.run(app, host="0.0.0.0", port=port)
