"""
사례 데이터 타입 정의
"""

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class Case:
    """사례 데이터 모델"""
    id: str                          # 고유 ID
    project_name: str                # 프로젝트명: [회사명] 프로젝트명
    grade: str                       # 등급 ('A', 'B', 'C')
    department: str                  # 실행부서
    industry: str                    # 업종
    business_overview: str           # 사업개요: 프로젝트배경 및 요약, 일정 및 마일스톤, 시스템설명
    keywords: List[str] = field(default_factory=list)   # 검색용 키워드
    category: Optional[str] = None   # 카테고리 (기존 호환성 유지)
    tags: Optional[List[str]] = None # 태그 (기존 호환성 유지)

    def to_dict(self) -> dict:
        """딕셔너리로 변환"""
        result = {
            "id": self.id,
            "projectName": self.project_name,
            "grade": self.grade,
            "department": self.department,
            "industry": self.industry,
            "businessOverview": self.business_overview,
            "keywords": self.keywords,
        }
        if self.category:
            result["category"] = self.category
        if self.tags:
            result["tags"] = self.tags
        return result

    def to_summary_dict(self) -> dict:
        """요약 딕셔너리로 변환 (목록 조회용)"""
        return {
            "id": self.id,
            "projectName": self.project_name,
            "grade": self.grade,
            "department": self.department,
            "industry": self.industry,
        }
