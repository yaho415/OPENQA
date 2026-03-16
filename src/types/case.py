"""
프로젝트 데이터 타입 정의
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Project:
    """프로젝트 데이터 모델 (project 테이블)"""
    project_code: str                          # 프로젝트 코드 (PK)
    project_name: str                          # 프로젝트 명
    grade_code: Optional[str] = None           # 등급
    sap_phase: Optional[str] = None            # 품의단계 (S, A, B, C)
    sales_dept_code: Optional[str] = None      # 실행부서
    project_from_date: Optional[str] = None    # 프로젝트 시작일 (yyyy-mm-dd)
    contract_account: Optional[str] = None     # 고객사
    industry_detail: Optional[str] = None      # 업종상세
    business_type: Optional[str] = None        # 사업유형 (유지보수, 신규, 지원)
    summary: Optional[str] = None              # 사업개요
    methodology_value: Optional[str] = None    # 방법론

    def to_dict(self) -> dict:
        """딕셔너리로 변환"""
        return {
            "projectCode": self.project_code,
            "projectName": self.project_name,
            "gradeCode": self.grade_code,
            "sapPhase": self.sap_phase,
            "salesDeptCode": self.sales_dept_code,
            "projectFromDate": self.project_from_date,
            "contractAccount": self.contract_account,
            "industryDetail": self.industry_detail,
            "businessType": self.business_type,
            "summary": self.summary,
            "methodologyValue": self.methodology_value,
        }

    def to_summary_dict(self) -> dict:
        """요약 딕셔너리로 변환 (목록 조회용)"""
        return {
            "projectCode": self.project_code,
            "projectName": self.project_name,
            "gradeCode": self.grade_code,
            "salesDeptCode": self.sales_dept_code,
            "industryDetail": self.industry_detail,
        }


# 하위 호환을 위한 별칭
Case = Project
