"""
유사사례를 추천하는 모듈 (벡터 기반 유사도 검색 + 키워드 기반 fallback)
"""

import re
from typing import Dict, List, Optional, Tuple

from src.types.case import Case
from src.keyword_extractor import KeywordExtractor
from src.database.db import get_database
from src.vector_embedder import get_vector_embedder


def _jaro_winkler_distance(s1: str, s2: str) -> float:
    """
    두 문자열 간 Jaro-Winkler 유사도 계산 (0~1, 1이 완전 일치)
    """
    if s1 == s2:
        return 1.0

    len_s1 = len(s1)
    len_s2 = len(s2)

    if len_s1 == 0 or len_s2 == 0:
        return 0.0

    # 매칭 윈도우
    match_distance = max(len_s1, len_s2) // 2 - 1
    if match_distance < 0:
        match_distance = 0

    s1_matches = [False] * len_s1
    s2_matches = [False] * len_s2

    matches = 0
    transpositions = 0

    # 매칭 문자 찾기
    for i in range(len_s1):
        start = max(0, i - match_distance)
        end = min(i + match_distance + 1, len_s2)
        for j in range(start, end):
            if s2_matches[j] or s1[i] != s2[j]:
                continue
            s1_matches[i] = True
            s2_matches[j] = True
            matches += 1
            break

    if matches == 0:
        return 0.0

    # 전치 수 계산
    k = 0
    for i in range(len_s1):
        if not s1_matches[i]:
            continue
        while not s2_matches[k]:
            k += 1
        if s1[i] != s2[k]:
            transpositions += 1
        k += 1

    jaro = (matches / len_s1 + matches / len_s2 + (matches - transpositions / 2) / matches) / 3

    # Winkler 보정 (공통 접두사 최대 4자)
    prefix = 0
    for i in range(min(len_s1, len_s2, 4)):
        if s1[i] == s2[i]:
            prefix += 1
        else:
            break

    return jaro + prefix * 0.1 * (1 - jaro)


class CaseRecommender:
    """유사사례를 추천하는 클래스 (벡터 기반 유사도 검색)"""

    def __init__(self):
        self.keyword_extractor = KeywordExtractor()
        self.embedder = get_vector_embedder()

    async def recommend_similar_cases(
        self,
        user_prompt: str,
        max_results: int = 5,
        provided_keywords: Optional[List[str]] = None,
    ) -> List[Dict]:
        """
        사용자 프롬프트를 기반으로 유사한 사례를 추천 (벡터 기반)

        Args:
            user_prompt: 사용자 프롬프트
            max_results: 추천할 최대 사례 수 (기본값: 5)
            provided_keywords: LLM이 추출한 키워드 배열 (선택적)

        Returns:
            추천된 사례 리스트 [{"case": Case, "score": float, "matched_keywords": list}]
        """
        db = get_database()

        try:
            # 1. 사용자 프롬프트를 벡터로 변환 (async)
            query_embedding = await self.embedder.embed(user_prompt)

            # 2. 벡터 유사도 검색
            vector_results = db.search_similar_cases_by_vector(
                query_embedding, max_results
            )

            # 3. 키워드 추출 (매칭 키워드 표시용)
            extracted_keywords = (
                provided_keywords
                if provided_keywords and len(provided_keywords) > 0
                else self.keyword_extractor.extract_keywords(user_prompt, 10)
            )

            # 4. 결과 포맷팅
            return [
                {
                    "case": case_item,
                    "score": similarity,
                    "matched_keywords": self._find_matched_keywords(
                        extracted_keywords, case_item
                    ),
                }
                for case_item, similarity in vector_results
            ]

        except Exception as e:
            # 벡터 검색 실패 시 키워드 기반 검색으로 fallback
            print(f"벡터 검색 실패, 키워드 기반 검색으로 전환: {e}")
            return await self.recommend_similar_cases_by_keyword(
                user_prompt, max_results, provided_keywords
            )

    async def recommend_similar_cases_by_keyword(
        self,
        user_prompt: str,
        max_results: int = 5,
        provided_keywords: Optional[List[str]] = None,
    ) -> List[Dict]:
        """
        키워드 기반 유사도 검색 (fallback)

        Args:
            user_prompt: 사용자 프롬프트
            max_results: 추천할 최대 사례 수
            provided_keywords: 제공된 키워드

        Returns:
            추천된 사례 리스트
        """
        # 키워드 추출
        extracted_keywords = (
            provided_keywords
            if provided_keywords and len(provided_keywords) > 0
            else self.keyword_extractor.extract_keywords(user_prompt, 10)
        )

        # 데이터베이스에서 사례 목록 가져오기
        db = get_database()
        cases_database = db.get_all_cases()

        # 각 사례에 대해 유사도 계산
        scored_cases = []
        for case_item in cases_database:
            score = self._calculate_similarity_score(
                extracted_keywords, case_item, user_prompt
            )
            matched_keywords = self._find_matched_keywords(
                extracted_keywords, case_item
            )
            scored_cases.append(
                {
                    "case": case_item,
                    "score": score,
                    "matched_keywords": matched_keywords,
                }
            )

        # 점수 순으로 정렬
        scored_cases.sort(key=lambda x: x["score"], reverse=True)

        return scored_cases[:max_results]

    def _calculate_similarity_score(
        self,
        keywords: List[str],
        case_item: Case,
        user_prompt: str,
    ) -> float:
        """
        키워드와 사례 간의 유사도 점수 계산

        Args:
            keywords: 추출된 키워드 배열
            case_item: 사례 객체
            user_prompt: 원본 사용자 프롬프트

        Returns:
            유사도 점수 (0-1)
        """
        score = 0.0
        match_count = 0

        # 키워드 매칭 점수 (40%)
        all_case_keywords = " ".join(
            [
                *[k.lower() for k in case_item.keywords],
                *[t.lower() for t in (case_item.tags or [])],
                case_item.project_name.lower(),
                case_item.business_overview.lower(),
                case_item.department.lower(),
                case_item.industry.lower(),
            ]
        )

        for keyword in keywords:
            keyword_lower = keyword.lower()
            if keyword_lower in all_case_keywords:
                match_count += 1
                score += 0.4
            else:
                # 부분 매칭 확인 (Jaro-Winkler 거리 사용)
                words = all_case_keywords.split()
                for word in words:
                    similarity = _jaro_winkler_distance(keyword_lower, word)
                    if similarity > 0.7:
                        score += 0.2 * similarity
                        break

        # 키워드 매칭 비율 점수 (30%)
        keyword_match_ratio = match_count / len(keywords) if keywords else 0.0
        score += keyword_match_ratio * 0.3

        # 텍스트 유사도 점수 (30%)
        prompt_words = user_prompt.lower().split()
        case_words = all_case_keywords.split()
        common_words = [
            w
            for w in prompt_words
            if any(cw in w or w in cw for cw in case_words)
        ]
        text_similarity = len(common_words) / len(prompt_words) if prompt_words else 0.0
        score += text_similarity * 0.3

        return min(score, 1.0)

    @staticmethod
    def _find_matched_keywords(
        keywords: List[str],
        case_item: Case,
    ) -> List[str]:
        """
        매칭된 키워드 찾기

        Args:
            keywords: 추출된 키워드 배열
            case_item: 사례 객체

        Returns:
            매칭된 키워드 배열
        """
        # 사례의 키워드와 태그를 정규화
        case_keywords = [
            k.lower().strip() for k in case_item.keywords
        ] + [t.lower().strip() for t in (case_item.tags or [])]

        # 사례의 텍스트 필드들을 단어 단위로 분리
        raw_words = (
            re.sub(r"[\[\]]", " ", case_item.project_name).lower().split()
            + case_item.business_overview.lower().split()
            + case_item.department.lower().split()
            + case_item.industry.lower().split()
        )
        case_text_words = [
            re.sub(r"[^\w가-힣]", "", w).strip()
            for w in raw_words
        ]
        case_text_words = [w for w in case_text_words if len(w) >= 2]

        all_case_kw = list(set(case_keywords + case_text_words))
        matched: List[str] = []

        for keyword in keywords:
            kw_lower = keyword.lower().strip()

            # 정확히 일치하는 키워드 확인
            if any(ck == kw_lower for ck in case_keywords):
                matched.append(keyword)
                continue

            # 사례 키워드가 사용자 키워드를 포함하는지 확인
            if any(
                kw_lower in ck and len(ck) >= len(kw_lower) for ck in case_keywords
            ):
                matched.append(keyword)
                continue

            # 텍스트 단어와 정확히 일치하는지 확인
            if any(ctw == kw_lower for ctw in case_text_words):
                matched.append(keyword)
                continue

            # 텍스트 단어가 사용자 키워드를 포함하는지 확인
            if len(kw_lower) >= 2 and any(
                kw_lower in ctw and len(ctw) >= len(kw_lower)
                for ctw in case_text_words
            ):
                matched.append(keyword)
                continue

        return matched

    # ──────────────────────────────────────────────────────────
    # 카테고리/등급/부서별 필터링
    # ──────────────────────────────────────────────────────────

    def get_cases_by_category(self, industry: str) -> List[Case]:
        """업종별로 사례 필터링"""
        db = get_database()
        return db.get_cases_by_industry(industry)

    def get_cases_by_grade(self, grade: str) -> List[Case]:
        """등급별로 사례 필터링"""
        db = get_database()
        return db.get_cases_by_grade(grade)

    def get_cases_by_department(self, department: str) -> List[Case]:
        """부서별로 사례 필터링"""
        db = get_database()
        return db.get_cases_by_department(department)

    def search_cases_by_keyword(self, keyword: str) -> List[Case]:
        """키워드로 사례 검색"""
        db = get_database()
        return db.search_cases_by_keyword(keyword)
