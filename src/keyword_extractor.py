"""
사용자 프롬프트에서 키워드를 추출하는 모듈
TF-IDF 기반 키워드 추출 및 한국어/영어 불용어 처리
"""

import re
import math
from collections import Counter
from typing import List


# 불용어 목록 (한국어 + 영어)
STOPWORDS = {
    # 영어 불용어
    "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "is", "are", "was", "were", "be", "been",
    "have", "has", "had", "do", "does", "did", "will", "would", "should",
    "can", "could", "may", "might", "shall", "not", "no", "it", "its",
    "this", "that", "these", "those", "i", "you", "he", "she", "we", "they",
    "me", "him", "her", "us", "them", "my", "your", "his", "our", "their",
    "what", "which", "who", "whom", "where", "when", "why", "how",
    "all", "each", "every", "both", "few", "more", "most", "other",
    "some", "such", "than", "too", "very", "just", "about", "above",
    "after", "again", "also", "any", "because", "before", "between",
    "into", "through", "during", "out", "off", "over", "under",
    # 한국어 불용어
    "이", "가", "을", "를", "에", "의", "와", "과", "으로", "로", "에서",
    "은", "는", "도", "만", "까지", "부터", "에게", "께", "한테", "더",
    "그", "저", "그것", "이것", "저것", "그런", "이런", "저런",
    "및", "등", "것", "수", "위해", "대한", "통해", "따라",
    "하는", "있는", "되는", "하여", "하고", "있으며", "합니다",
    "그리고", "하지만", "그러나", "또는", "또한", "때문에",
}


class KeywordExtractor:
    """사용자 프롬프트에서 키워드를 추출하는 클래스"""

    def __init__(self):
        pass

    @staticmethod
    def _tokenize(text: str) -> List[str]:
        """
        텍스트를 토큰화 (한국어 + 영어 지원)
        - 한글 단어, 영어 단어, 숫자 조합을 토큰으로 추출
        """
        # 한글 단어, 영어 단어, 숫자+영어 조합 등 추출
        tokens = re.findall(r"[가-힣]+|[a-zA-Z]+(?:\d+[a-zA-Z]*)*|\d+[a-zA-Z]+", text.lower())
        return tokens

    @staticmethod
    def _remove_stopwords(tokens: List[str]) -> List[str]:
        """불용어 제거 및 최소 길이 필터링"""
        return [t for t in tokens if t not in STOPWORDS and len(t) >= 2]

    def extract_keywords(self, text: str, max_keywords: int = 5) -> List[str]:
        """
        텍스트에서 주요 키워드를 추출 (TF-IDF 기반)

        Args:
            text: 사용자 프롬프트 텍스트
            max_keywords: 추출할 최대 키워드 수 (기본값: 5)

        Returns:
            추출된 키워드 배열
        """
        tokens = self._tokenize(text)
        filtered_tokens = self._remove_stopwords(tokens)

        if not filtered_tokens:
            return []

        # TF (Term Frequency) 계산
        token_counts = Counter(filtered_tokens)
        total_tokens = len(filtered_tokens)

        # 단일 문서이므로 IDF 대신 빈도와 위치 기반 점수 사용
        keyword_scores = []
        unique_tokens = list(dict.fromkeys(filtered_tokens))  # 순서 유지하면서 중복 제거

        for token in unique_tokens:
            tf = token_counts[token] / total_tokens

            # 길이 보너스: 긴 단어일수록 더 의미 있는 경향
            length_bonus = min(len(token) / 10.0, 0.5)

            # 빈도 점수
            freq_score = tf

            # 최종 점수
            score = freq_score + length_bonus

            keyword_scores.append((token, score))

        # 점수 순으로 정렬
        keyword_scores.sort(key=lambda x: x[1], reverse=True)

        return [kw for kw, _ in keyword_scores[:max_keywords]]

    def extract_noun_keywords(self, text: str, max_keywords: int = 5) -> List[str]:
        """
        텍스트에서 명사 키워드를 추출 (간이 버전)

        Args:
            text: 사용자 프롬프트 텍스트
            max_keywords: 추출할 최대 키워드 수

        Returns:
            추출된 키워드 배열
        """
        tokens = self._tokenize(text)
        filtered = [t for t in tokens if len(t) >= 2]
        # 순서 유지하면서 중복 제거
        seen = set()
        result = []
        for t in filtered:
            if t not in seen:
                seen.add(t)
                result.append(t)
        return result[:max_keywords]
