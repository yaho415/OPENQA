"""
FastAPI REST 서버 - 유사 프로젝트 추천 API

최적화:
  - 키워드 추출: 내장 TF-IDF (Qwen LLM 제거로 ~11초 단축)
  - HTTP 클라이언트: httpx AsyncClient (Keep-Alive 연결 재사용)
  - 임베딩 캐시: LRU 캐시 (반복 질의 즉시 응답)
  - 모델 워밍업: 서버 시작 시 BGE-M3 모델을 메모리에 프리로딩
"""

import os
import sys
import time
from contextlib import asynccontextmanager

# 프로젝트 루트를 sys.path에 추가
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from typing import List

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv

from src.case_recommender import CaseRecommender
from src.keyword_extractor import KeywordExtractor
from src.vector_embedder import get_vector_embedder
from src.database.db import get_database

load_dotenv()


# ──────────────────────────────────────────────────────────
# Lifespan: 서버 시작/종료 시 실행할 로직
# ──────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """서버 시작 시 모델 워밍업, 종료 시 리소스 정리"""
    # ── Startup ──
    embedder = get_vector_embedder()
    await embedder.warm_up()
    print("[READY] 서버 준비 완료 - 모든 모델이 메모리에 로딩됨")
    yield
    # ── Shutdown ──
    await embedder.close()
    print("[SHUTDOWN] 리소스 정리 완료")


# ──────────────────────────────────────────────────────────
# FastAPI 앱 설정
# ──────────────────────────────────────────────────────────
app = FastAPI(
    title="OpenQA 유사 프로젝트 추천 서비스",
    description="사용자 프롬프트를 기반으로 유사 프로젝트를 추천하는 REST API",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

case_recommender = CaseRecommender()
keyword_extractor = KeywordExtractor()


# ──────────────────────────────────────────────────────────
# 요청/응답 모델
# ──────────────────────────────────────────────────────────
class RecommendRequest(BaseModel):
    prompt: str
    max_results: int = 5


class ExtractKeywordsRequest(BaseModel):
    text: str
    max_keywords: int = 10


class SearchByKeywordRequest(BaseModel):
    keyword: str


class GetByCategoryRequest(BaseModel):
    category: str


# ──────────────────────────────────────────────────────────
# API 엔드포인트
# ──────────────────────────────────────────────────────────

@app.post("/api/recommend")
async def recommend_cases(req: RecommendRequest):
    """유사 사례 추천 API"""
    if not req.prompt or not req.prompt.strip():
        raise HTTPException(status_code=400, detail="prompt는 필수 파라미터입니다.")

    try:
        total_start = time.time()

        # [STEP 1] TF-IDF 키워드 추출 (내장, 즉시 완료)
        t1 = time.time()
        keywords = keyword_extractor.extract_keywords(req.prompt, 10)
        t1_elapsed = time.time() - t1
        print(f"[TIMING] Step1 - TF-IDF 키워드 추출: {t1_elapsed:.3f}초")

        # [STEP 2] 유사 사례 추천 (벡터 임베딩 + DB 검색)
        t2 = time.time()
        recommendations = await case_recommender.recommend_similar_cases(
            req.prompt, req.max_results, keywords
        )
        t2_elapsed = time.time() - t2
        print(f"[TIMING] Step2 - 벡터 임베딩 + DB 검색: {t2_elapsed:.2f}초")

        # [STEP 3] 결과 포맷팅
        result = [
            {
                "id": rec["case"].id,
                "projectName": rec["case"].project_name,
                "grade": rec["case"].grade,
                "department": rec["case"].department,
                "industry": rec["case"].industry,
                "businessOverview": rec["case"].business_overview,
                "score": round(rec["score"] * 100) / 100,
                "matchedKeywords": rec["matched_keywords"],
            }
            for rec in recommendations
        ]

        total_elapsed = time.time() - total_start
        print(f"[TIMING] === 전체 소요시간: {total_elapsed:.2f}초 ===")

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
            detail=f"사례 추천 중 오류가 발생했습니다: {str(e)}",
        )


@app.post("/api/extract-keywords")
async def extract_keywords_api(req: ExtractKeywordsRequest):
    """키워드 추출 API"""
    if not req.text or not req.text.strip():
        raise HTTPException(status_code=400, detail="text는 필수 파라미터입니다.")

    try:
        keywords = keyword_extractor.extract_keywords(req.text, req.max_keywords)
        return {
            "success": True,
            "text": req.text,
            "keywords": keywords,
            "count": len(keywords),
        }
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"키워드 추출 중 오류가 발생했습니다: {str(e)}",
        )


@app.post("/api/search")
async def search_by_keyword(req: SearchByKeywordRequest):
    """키워드로 사례 검색 API"""
    if not req.keyword or not req.keyword.strip():
        raise HTTPException(status_code=400, detail="keyword는 필수 파라미터입니다.")

    try:
        cases = case_recommender.search_cases_by_keyword(req.keyword)
        return {
            "success": True,
            "keyword": req.keyword,
            "cases": [c.to_summary_dict() for c in cases],
            "total": len(cases),
        }
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"사례 검색 중 오류가 발생했습니다: {str(e)}",
        )


@app.post("/api/cases/category")
async def get_cases_by_category(req: GetByCategoryRequest):
    """업종별 사례 조회 API"""
    try:
        cases = case_recommender.get_cases_by_category(req.category)
        return {
            "success": True,
            "category": req.category,
            "cases": [c.to_summary_dict() for c in cases],
            "total": len(cases),
        }
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"사례 조회 중 오류가 발생했습니다: {str(e)}",
        )


@app.get("/api/cases")
async def list_all_cases():
    """모든 사례 목록 조회 API"""
    try:
        db = get_database()
        cases = db.get_all_cases()
        return {
            "success": True,
            "cases": [
                {
                    **c.to_summary_dict(),
                    "keywords": c.keywords,
                }
                for c in cases
            ],
            "total": len(cases),
        }
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"사례 목록 조회 중 오류가 발생했습니다: {str(e)}",
        )


@app.get("/api/health")
async def health_check():
    """건강 체크 API (캐시 상태 포함)"""
    db_status = "unknown"
    try:
        db = get_database()
        db.get_all_cases()
        db_status = "connected"
    except Exception:
        db_status = "disconnected"

    embedder = get_vector_embedder()

    return {
        "status": "ok",
        "database": db_status,
        "embedding_cache": embedder.get_cache_stats(),
    }


# ──────────────────────────────────────────────────────────
# 서버 실행
# ──────────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    import sys

    # Windows cp949 인코딩 문제 해결
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    port = int(os.getenv("PORT", "3001"))
    print(f"[START] http://localhost:{port}")
    print(f"[MODE] TF-IDF keyword extractor (no LLM)")
    print(f"[DOCS] http://localhost:{port}/docs")

    uvicorn.run(app, host="0.0.0.0", port=port)
