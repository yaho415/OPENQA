"""
유사 프로젝트를 추천하는 모듈 (벡터 기반 유사도 검색 + 키워드 기반 fallback)
"""

import re
from typing import Dict, List, Optional, Tuple

from src.types.case import Project
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

    match_distance = max(len_s1, len_s2) // 2 - 1
    if match_distance < 0:
        match_distance = 0

    s1_matches = [False] * len_s1
    s2_matches = [False] * len_s2

    matches = 0
    transpositions = 0

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

    prefix = 0
    for i in range(min(len_s1, len_s2, 4)):
        if s1[i] == s2[i]:
            prefix += 1
        else:
            break

    return jaro + prefix * 0.1 * (1 - jaro)


class CaseRecommender:
    """유사 프로젝트를 추천하는 클래스 (벡터 기반 유사도 검색)"""

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
        사용자 프롬프트를 기반으로 유사한 프로젝트를 추천 (벡터 기반)

        Args:
            user_prompt: 사용자 프롬프트
            max_results: 추천할 최대 프로젝트 수 (기본값: 5)
            provided_keywords: LLM이 추출한 키워드 배열 (선택적)

        Returns:
            추천된 프로젝트 리스트 [{"case": Project, "score": float, "matched_keywords": list}]
        """
        db = get_database()

        try:
            # 1. 사용자 프롬프트를 벡터로 변환
            query_embedding = await self.embedder.embed(user_prompt)

            # 2. 벡터 유사도 검색
            vector_results = db.search_similar_projects_by_vector(
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
                    "case": project_item,
                    "score": similarity,
                    "matched_keywords": self._find_matched_keywords(
                        extracted_keywords, project_item
                    ),
                }
                for project_item, similarity in vector_results
            ]

        except Exception as e:
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
        """키워드 기반 유사도 검색 (fallback)"""
        extracted_keywords = (
            provided_keywords
            if provided_keywords and len(provided_keywords) > 0
            else self.keyword_extractor.extract_keywords(user_prompt, 10)
        )

        db = get_database()
        projects = db.get_all_projects()

        scored_projects = []
        for project_item in projects:
            score = self._calculate_similarity_score(
                extracted_keywords, project_item, user_prompt
            )
            matched_keywords = self._find_matched_keywords(
                extracted_keywords, project_item
            )
            scored_projects.append(
                {
                    "case": project_item,
                    "score": score,
                    "matched_keywords": matched_keywords,
                }
            )

        scored_projects.sort(key=lambda x: x["score"], reverse=True)
        return scored_projects[:max_results]

    def _calculate_similarity_score(
        self,
        keywords: List[str],
        project_item: Project,
        user_prompt: str,
    ) -> float:
        """키워드와 프로젝트 간의 유사도 점수 계산"""
        score = 0.0
        match_count = 0

        # 프로젝트의 텍스트 필드들을 결합
        all_text = " ".join(filter(None, [
            (project_item.project_name or "").lower(),
            (project_item.summary or "").lower(),
            (project_item.sales_dept_code or "").lower(),
            (project_item.industry_detail or "").lower(),
            (project_item.contract_account or "").lower(),
            (project_item.business_type or "").lower(),
            (project_item.methodology_value or "").lower(),
        ]))

        for keyword in keywords:
            keyword_lower = keyword.lower()
            if keyword_lower in all_text:
                match_count += 1
                score += 0.4
            else:
                words = all_text.split()
                for word in words:
                    similarity = _jaro_winkler_distance(keyword_lower, word)
                    if similarity > 0.7:
                        score += 0.2 * similarity
                        break

        keyword_match_ratio = match_count / len(keywords) if keywords else 0.0
        score += keyword_match_ratio * 0.3

        prompt_words = user_prompt.lower().split()
        case_words = all_text.split()
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
        project_item: Project,
    ) -> List[str]:
        """매칭된 키워드 찾기"""
        raw_words = (
            re.sub(r"[\[\]]", " ", project_item.project_name or "").lower().split()
            + (project_item.summary or "").lower().split()
            + (project_item.sales_dept_code or "").lower().split()
            + (project_item.industry_detail or "").lower().split()
            + (project_item.contract_account or "").lower().split()
            + (project_item.business_type or "").lower().split()
        )
        text_words = [
            re.sub(r"[^\w가-힣]", "", w).strip()
            for w in raw_words
        ]
        text_words = [w for w in text_words if len(w) >= 2]

        matched: List[str] = []

        for keyword in keywords:
            kw_lower = keyword.lower().strip()

            if any(tw == kw_lower for tw in text_words):
                matched.append(keyword)
                continue

            if len(kw_lower) >= 2 and any(
                kw_lower in tw and len(tw) >= len(kw_lower)
                for tw in text_words
            ):
                matched.append(keyword)
                continue

        return matched

    # ──────────────────────────────────────────────────────────
    # 필터링
    # ──────────────────────────────────────────────────────────

    def get_cases_by_category(self, industry: str) -> List[Project]:
        db = get_database()
        return db.get_projects_by_industry(industry)

    def get_cases_by_grade(self, grade: str) -> List[Project]:
        db = get_database()
        return db.get_projects_by_grade(grade)

    def search_cases_by_keyword(self, keyword: str) -> List[Project]:
        db = get_database()
        return db.search_projects_by_keyword(keyword)
