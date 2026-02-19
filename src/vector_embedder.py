"""
텍스트를 벡터 임베딩으로 변환하는 모듈 (Ollama BGE-M3 모델 사용)

최적화:
  - httpx.AsyncClient: 연결 재사용 (Keep-Alive) + 네이티브 async
  - LRU 캐시: 동일/유사 프롬프트 반복 시 Ollama 재호출 방지
"""

import hashlib
import os
import time
from collections import OrderedDict
from typing import Dict, List, Optional, Tuple

import httpx
from dotenv import load_dotenv

load_dotenv()


class EmbeddingCache:
    """LRU 임베딩 캐시 (최근 사용 순으로 유지)"""

    def __init__(self, max_size: int = 200):
        self._cache: OrderedDict[str, List[float]] = OrderedDict()
        self._max_size = max_size
        self._hits = 0
        self._misses = 0

    @staticmethod
    def _make_key(text: str) -> str:
        """텍스트를 캐시 키로 변환 (SHA-256 해시)"""
        return hashlib.sha256(text.strip().encode("utf-8")).hexdigest()

    def get(self, text: str) -> Optional[List[float]]:
        """캐시에서 임베딩 조회"""
        key = self._make_key(text)
        if key in self._cache:
            self._hits += 1
            self._cache.move_to_end(key)  # 최근 사용으로 이동
            return self._cache[key]
        self._misses += 1
        return None

    def put(self, text: str, embedding: List[float]) -> None:
        """캐시에 임베딩 저장"""
        key = self._make_key(text)
        if key in self._cache:
            self._cache.move_to_end(key)
        else:
            if len(self._cache) >= self._max_size:
                self._cache.popitem(last=False)  # 가장 오래된 항목 제거
            self._cache[key] = embedding

    @property
    def stats(self) -> dict:
        total = self._hits + self._misses
        return {
            "size": len(self._cache),
            "max_size": self._max_size,
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": f"{self._hits / total * 100:.1f}%" if total > 0 else "N/A",
        }


class VectorEmbedder:
    """텍스트를 벡터 임베딩으로 변환하는 클래스 (Ollama BGE-M3 모델 사용)

    최적화:
      - httpx.AsyncClient 로 Keep-Alive 연결 재사용
      - LRU 캐시로 중복 임베딩 호출 제거
    """

    MODEL_NAME = "bge-m3"
    DIMENSION = 1024

    def __init__(self):
        self.ollama_url: str = os.getenv("OLLAMA_URL", "http://localhost:11434")
        self._initialized: bool = False
        self._cache = EmbeddingCache(max_size=200)

        # httpx AsyncClient: 연결 재사용 (Keep-Alive) + 타임아웃 설정
        self._client = httpx.AsyncClient(
            base_url=self.ollama_url,
            timeout=httpx.Timeout(60.0, connect=10.0),
            limits=httpx.Limits(
                max_connections=10,
                max_keepalive_connections=5,
                keepalive_expiry=30.0,
            ),
        )

    async def _initialize_model(self) -> None:
        """Ollama 서버 연결 확인 및 모델 초기화"""
        if self._initialized:
            return

        print("Ollama BGE-M3 임베딩 모델 초기화 중...")
        print(f"   Ollama URL: {self.ollama_url}")
        print(f"   모델: {self.MODEL_NAME}")
        print(f"   차원: {self.DIMENSION}차원")

        try:
            resp = await self._client.get("/api/tags")
            resp.raise_for_status()

            models_data = resp.json()
            available_models = models_data.get("models", [])
            model_exists = any(
                m.get("name") == self.MODEL_NAME or "bge-m3" in m.get("name", "")
                for m in available_models
            )

            if not model_exists:
                model_names = [m.get("name", "") for m in available_models]
                print(f'  모델 "{self.MODEL_NAME}"을 찾을 수 없습니다.')
                print(f"   사용 가능한 모델: {', '.join(model_names)}")
                print(f"   모델을 다운로드하세요: ollama pull {self.MODEL_NAME}")

            self._initialized = True
            print("Ollama 연결 확인 완료")

        except Exception as e:
            print(f"Ollama 초기화 실패: {e}")
            raise

    async def warm_up(self) -> None:
        """모델 워밍업: 서버 시작 시 더미 임베딩을 실행하여 모델을 메모리에 로딩"""
        print("[WARM-UP] BGE-M3 모델 워밍업 시작...")
        t_start = time.time()
        try:
            await self.embed("warm-up embedding test")
            elapsed = time.time() - t_start
            print(f"[WARM-UP] BGE-M3 모델 워밍업 완료 ({elapsed:.2f}초)")
        except Exception as e:
            print(f"[WARM-UP] 워밍업 실패 (무시하고 계속): {e}")

    async def embed(self, text: str) -> List[float]:
        """
        텍스트를 벡터 임베딩으로 변환 (Ollama API 사용)

        최적화:
          - 캐시 히트 시 Ollama 호출 없이 즉시 반환
          - httpx Keep-Alive로 TCP 재연결 비용 제거

        Args:
            text: 임베딩할 텍스트

        Returns:
            벡터 배열 (1024차원)
        """
        await self._initialize_model()

        processed_text = text.strip()
        if not processed_text:
            raise ValueError("빈 텍스트는 임베딩할 수 없습니다.")

        # 캐시 확인
        cached = self._cache.get(processed_text)
        if cached is not None:
            return cached

        try:
            resp = await self._client.post(
                "/api/embeddings",
                json={"model": self.MODEL_NAME, "prompt": processed_text},
            )
            resp.raise_for_status()
            data = resp.json()

            raw_embedding = data.get("embedding")
            if raw_embedding is None:
                raise ValueError("Ollama 응답에서 embedding을 찾을 수 없습니다.")

            if isinstance(raw_embedding, dict):
                embedding = [float(v) for v in raw_embedding.values()]
            elif isinstance(raw_embedding, list):
                embedding = [float(v) for v in raw_embedding]
            else:
                raise ValueError("Ollama 응답의 embedding 형식이 올바르지 않습니다.")

            # 차원 확인 및 조정
            if len(embedding) != self.DIMENSION:
                print(
                    f"  임베딩 차원이 예상과 다릅니다. 예상: {self.DIMENSION}, 실제: {len(embedding)}"
                )
                if len(embedding) < self.DIMENSION:
                    embedding.extend([0.0] * (self.DIMENSION - len(embedding)))
                else:
                    embedding = embedding[: self.DIMENSION]

            # 캐시에 저장
            self._cache.put(processed_text, embedding)

            return embedding

        except httpx.HTTPError as e:
            print(f"임베딩 생성 중 오류: {e}")
            raise

    async def embed_batch(
        self, texts: List[str], batch_size: int = 3
    ) -> List[List[float]]:
        """
        여러 텍스트를 일괄 임베딩 (async 순차 처리)

        Args:
            texts: 임베딩할 텍스트 배열
            batch_size: 배치 크기

        Returns:
            벡터 배열의 배열
        """
        await self._initialize_model()
        embeddings: List[List[float]] = []

        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            print(
                f"   배치 처리 중: {i + 1}-{min(i + batch_size, len(texts))}/{len(texts)}"
            )

            for text in batch:
                embedding = await self.embed(text)
                embeddings.append(embedding)

        return embeddings

    @staticmethod
    def create_embedding_text(case_item) -> str:
        """
        사례 데이터를 임베딩하기 위한 텍스트 생성

        Args:
            case_item: Case 객체 또는 유사한 속성을 가진 딕셔너리

        Returns:
            임베딩용 텍스트
        """
        if hasattr(case_item, "project_name"):
            parts = [
                case_item.project_name,
                case_item.business_overview,
                case_item.department,
                case_item.industry,
                *case_item.keywords,
                *(case_item.tags or []),
            ]
        else:
            parts = [
                case_item.get("project_name", ""),
                case_item.get("business_overview", ""),
                case_item.get("department", ""),
                case_item.get("industry", ""),
                *case_item.get("keywords", []),
                *case_item.get("tags", []),
            ]

        return " ".join(p for p in parts if p and p.strip())

    def get_dimension(self) -> int:
        """임베딩 차원 반환"""
        return self.DIMENSION

    def get_model_name(self) -> str:
        """모델 이름 반환"""
        return self.MODEL_NAME

    def get_cache_stats(self) -> dict:
        """캐시 통계 반환"""
        return self._cache.stats

    async def close(self) -> None:
        """HTTP 클라이언트 종료"""
        await self._client.aclose()


# ──────────────────────────────────────────────────────────
# 싱글톤
# ──────────────────────────────────────────────────────────

_embedder_instance: Optional[VectorEmbedder] = None


def get_vector_embedder() -> VectorEmbedder:
    """벡터 임베딩 싱글톤 인스턴스 반환"""
    global _embedder_instance
    if _embedder_instance is None:
        _embedder_instance = VectorEmbedder()
    return _embedder_instance
