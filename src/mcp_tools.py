"""
MCP 도구 함수들 - FastAPI와 MCP 서버에서 공통으로 사용

이 모듈은 MCP 서버의 도구 함수들을 정의하며,
FastAPI 서버에서도 직접 호출할 수 있습니다.
"""

import json
import os
import time
from pathlib import Path
from typing import Optional, List, Dict

import pandas as pd

from src.case_recommender import CaseRecommender
from src.keyword_extractor import KeywordExtractor
from src.database.db import get_database
from src.vector_embedder import get_vector_embedder
from src.types.case import Project

# 싱글톤 인스턴스
_recommender: Optional[CaseRecommender] = None
_extractor: Optional[KeywordExtractor] = None


def get_recommender() -> CaseRecommender:
    """CaseRecommender 싱글톤"""
    global _recommender
    if _recommender is None:
        _recommender = CaseRecommender()
    return _recommender


def get_extractor() -> KeywordExtractor:
    """KeywordExtractor 싱글톤"""
    global _extractor
    if _extractor is None:
        _extractor = KeywordExtractor()
    return _extractor


async def recommend_projects_tool(query: str, max_results: int = 5) -> Dict:
    """
    유사 프로젝트 추천 도구 (공통 함수)
    
    MCP 서버와 FastAPI 서버에서 공통으로 사용됩니다.
    
    Args:
        query: 검색할 프로젝트 설명
        max_results: 반환할 최대 결과 수 (기본값: 5, 최대: 10)
    
    Returns:
        추천 결과 딕셔너리
    """
    start_time = time.time()
    max_results = min(max_results, 10)
    
    recommender = get_recommender()
    extractor = get_extractor()
    
    keywords = extractor.extract_keywords(query, 10)
    recommendations = await recommender.recommend_similar_cases(
        query, max_results, keywords
    )

    results = []
    for rec in recommendations:
        project = rec["case"]
        summary = (project.summary or "").replace("프로젝트 배경 및 요약: ", "")
        results.append({
            "projectCode": project.project_code,
            "projectName": project.project_name,
            "gradeCode": project.grade_code,
            "salesDeptCode": project.sales_dept_code,
            "contractAccount": project.contract_account,
            "industryDetail": project.industry_detail,
            "businessType": project.business_type,
            "summary": summary,
            "methodologyValue": project.methodology_value,
            "score": round(rec["score"] * 100) / 100,
            "matchedKeywords": rec["matched_keywords"],
        })

    if not results:
        return {
            "query": query,
            "extractedKeywords": keywords,
            "totalResults": 0,
            "timingSeconds": round(time.time() - start_time, 2),
            "recommendations": [],
            "message": "검색 조건과 일치하는 프로젝트가 없습니다. 다른 키워드로 다시 검색해보세요."
        }

    elapsed = time.time() - start_time
    output = {
        "query": query,
        "extractedKeywords": keywords,
        "totalResults": len(results),
        "timingSeconds": round(elapsed, 2),
        "recommendations": results,
    }

    return output


async def update_projects_from_excel(file_path: str) -> Dict:
    """
    Excel 파일(xlsx)을 읽어서 프로젝트 현황(project 테이블)을 업데이트하는 도구
    
    MCP 서버와 FastAPI 서버에서 공통으로 사용됩니다.
    
    Args:
        file_path: Excel 파일 경로 (절대 경로 또는 상대 경로)
    
    Returns:
        업데이트 결과 딕셔너리
    """
    start_time = time.time()
    db = get_database()
    embedder = get_vector_embedder()
    
    # 파일 경로 확인
    file_path_obj = Path(file_path)
    if not file_path_obj.exists():
        return {
            "success": False,
            "message": f"파일을 찾을 수 없습니다: {file_path}",
            "updatedCount": 0,
            "errorCount": 0,
            "timingSeconds": round(time.time() - start_time, 2),
        }
    
    if not file_path_obj.suffix.lower() in ['.xlsx', '.xls']:
        return {
            "success": False,
            "message": f"지원하지 않는 파일 형식입니다. .xlsx 또는 .xls 파일만 지원합니다.",
            "updatedCount": 0,
            "errorCount": 0,
            "timingSeconds": round(time.time() - start_time, 2),
        }
    
    try:
        # Excel 파일 읽기
        df = pd.read_excel(file_path, engine='openpyxl')
        
        # 컬럼명을 소문자로 정규화 (대소문자 무시)
        df.columns = df.columns.str.lower().str.strip()
        
        # 필수 컬럼 확인 (project 테이블 기준)
        required_columns = ['project_code', 'project_name']
        missing_columns = [col for col in required_columns if col not in df.columns]
        if missing_columns:
            return {
                "success": False,
                "message": f"필수 컬럼이 없습니다: {', '.join(missing_columns)}",
                "updatedCount": 0,
                "errorCount": 0,
                "timingSeconds": round(time.time() - start_time, 2),
            }
        
        updated_count = 0
        inserted_count = 0
        skipped_count = 0
        error_count = 0
        updated_codes = []
        inserted_codes = []
        errors = []
        
        # Excel에 존재하는 컬럼 목록 (비교 시 Excel에 있는 필드만 비교)
        excel_columns = set(df.columns)
        
        # 값 정규화 함수 (날짜 형식, None/빈문자열 통일)
        def normalize_value(val, field_name=None):
            """비교를 위한 값 정규화"""
            if val is None:
                return None
            val = str(val).strip()
            if val in ('', 'None', 'nan', 'NaT'):
                return None
            # 날짜 필드: "2026-01-01 00:00:00" → "2026-01-01"
            if field_name == 'project_from_date' and len(val) > 10:
                val = val[:10]
            return val
        
        # 필드명 매핑 (Excel 소문자 컬럼 → to_dict camelCase 키)
        FIELD_MAP = {
            'project_code': 'projectCode',
            'project_name': 'projectName',
            'grade_code': 'gradeCode',
            'sap_phase': 'sapPhase',
            'sales_dept_code': 'salesDeptCode',
            'project_from_date': 'projectFromDate',
            'contract_account': 'contractAccount',
            'industry_detail': 'industryDetail',
            'business_type': 'businessType',
            'summary': 'summary',
            'methodology_value': 'methodologyValue',
        }
        
        # 각 행 처리
        for idx, row in df.iterrows():
            try:
                project_code = str(row['project_code']).strip()
                if not project_code or project_code in ('', 'None', 'nan'):
                    error_count += 1
                    errors.append(f"행 {idx + 2}: project_code가 비어있습니다.")
                    continue
                
                # 기존 데이터 조회
                existing = db.get_project_by_code(project_code)
                
                if existing:
                    # ── 기존 프로젝트: Excel에 있는 필드만 비교하여 변경 확인 ──
                    existing_dict = existing.to_dict()
                    has_changes = False
                    changed_fields = []
                    
                    for excel_col, dict_key in FIELD_MAP.items():
                        if excel_col not in excel_columns:
                            continue  # Excel에 없는 컬럼은 비교하지 않음
                        if excel_col == 'project_code':
                            continue  # PK는 비교 대상 아님
                        
                        excel_val = normalize_value(
                            row.get(excel_col), field_name=excel_col
                        ) if pd.notna(row.get(excel_col)) else None
                        
                        db_val = normalize_value(
                            existing_dict.get(dict_key), field_name=excel_col
                        )
                        
                        if excel_val != db_val:
                            has_changes = True
                            changed_fields.append(f"{excel_col}: '{db_val}' → '{excel_val}'")
                    
                    if has_changes:
                        # 변경된 필드만 반영하고, Excel에 없는 필드는 기존 값 유지
                        merged_project = Project(
                            project_code=project_code,
                            project_name=(
                                normalize_value(row['project_name'])
                                if 'project_name' in excel_columns and pd.notna(row.get('project_name'))
                                else existing.project_name
                            ),
                            grade_code=(
                                normalize_value(row.get('grade_code'))
                                if 'grade_code' in excel_columns and pd.notna(row.get('grade_code'))
                                else existing.grade_code
                            ),
                            sap_phase=(
                                normalize_value(row.get('sap_phase'))
                                if 'sap_phase' in excel_columns and pd.notna(row.get('sap_phase'))
                                else existing.sap_phase
                            ),
                            sales_dept_code=(
                                normalize_value(row.get('sales_dept_code'))
                                if 'sales_dept_code' in excel_columns and pd.notna(row.get('sales_dept_code'))
                                else existing.sales_dept_code
                            ),
                            project_from_date=(
                                normalize_value(row.get('project_from_date'), 'project_from_date')
                                if 'project_from_date' in excel_columns and pd.notna(row.get('project_from_date'))
                                else existing.project_from_date
                            ),
                            contract_account=(
                                normalize_value(row.get('contract_account'))
                                if 'contract_account' in excel_columns and pd.notna(row.get('contract_account'))
                                else existing.contract_account
                            ),
                            industry_detail=(
                                normalize_value(row.get('industry_detail'))
                                if 'industry_detail' in excel_columns and pd.notna(row.get('industry_detail'))
                                else existing.industry_detail
                            ),
                            business_type=(
                                normalize_value(row.get('business_type'))
                                if 'business_type' in excel_columns and pd.notna(row.get('business_type'))
                                else existing.business_type
                            ),
                            summary=(
                                normalize_value(row.get('summary'))
                                if 'summary' in excel_columns and pd.notna(row.get('summary'))
                                else existing.summary
                            ),
                            methodology_value=(
                                normalize_value(row.get('methodology_value'))
                                if 'methodology_value' in excel_columns and pd.notna(row.get('methodology_value'))
                                else existing.methodology_value
                            ),
                        )
                        
                        db.update_project(merged_project)
                        
                        # 임베딩 재생성
                        embedding_text = embedder.create_embedding_text(merged_project)
                        embedding = await embedder.embed(embedding_text)
                        db.update_project_embedding(project_code, embedding)
                        
                        updated_count += 1
                        updated_codes.append(project_code)
                        print(f"[UPDATE] {project_code} 업데이트 완료 (변경: {', '.join(changed_fields)})")
                    else:
                        skipped_count += 1
                        print(f"[SKIP] {project_code} - 변경 사항 없음")
                
                else:
                    # ── 신규 프로젝트: INSERT ──
                    new_project = Project(
                        project_code=project_code,
                        project_name=normalize_value(row['project_name']) or '',
                        grade_code=normalize_value(row.get('grade_code')) if 'grade_code' in excel_columns and pd.notna(row.get('grade_code')) else None,
                        sap_phase=normalize_value(row.get('sap_phase')) if 'sap_phase' in excel_columns and pd.notna(row.get('sap_phase')) else None,
                        sales_dept_code=normalize_value(row.get('sales_dept_code')) if 'sales_dept_code' in excel_columns and pd.notna(row.get('sales_dept_code')) else None,
                        project_from_date=normalize_value(row.get('project_from_date'), 'project_from_date') if 'project_from_date' in excel_columns and pd.notna(row.get('project_from_date')) else None,
                        contract_account=normalize_value(row.get('contract_account')) if 'contract_account' in excel_columns and pd.notna(row.get('contract_account')) else None,
                        industry_detail=normalize_value(row.get('industry_detail')) if 'industry_detail' in excel_columns and pd.notna(row.get('industry_detail')) else None,
                        business_type=normalize_value(row.get('business_type')) if 'business_type' in excel_columns and pd.notna(row.get('business_type')) else None,
                        summary=normalize_value(row.get('summary')) if 'summary' in excel_columns and pd.notna(row.get('summary')) else None,
                        methodology_value=normalize_value(row.get('methodology_value')) if 'methodology_value' in excel_columns and pd.notna(row.get('methodology_value')) else None,
                    )
                    
                    db.insert_project(new_project)
                    
                    # 임베딩 생성
                    embedding_text = embedder.create_embedding_text(new_project)
                    embedding = await embedder.embed(embedding_text)
                    db.update_project_embedding(project_code, embedding)
                    
                    inserted_count += 1
                    inserted_codes.append(project_code)
                    print(f"[INSERT] {project_code} 신규 등록 완료")
                    
            except Exception as e:
                error_count += 1
                error_msg = f"행 {idx + 2} (code: {row.get('project_code', 'N/A')}): {str(e)}"
                errors.append(error_msg)
                print(f"[ERROR] {error_msg}")
        
        elapsed = time.time() - start_time
        
        summary_parts = []
        if inserted_count > 0:
            summary_parts.append(f"신규 등록 {inserted_count}개")
        if updated_count > 0:
            summary_parts.append(f"업데이트 {updated_count}개")
        if skipped_count > 0:
            summary_parts.append(f"변경없음 {skipped_count}개")
        if error_count > 0:
            summary_parts.append(f"오류 {error_count}개")
        
        result = {
            "success": True,
            "message": f"처리 완료: {', '.join(summary_parts)}",
            "insertedCount": inserted_count,
            "updatedCount": updated_count,
            "skippedCount": skipped_count,
            "errorCount": error_count,
            "insertedIds": inserted_codes if inserted_codes else None,
            "updatedIds": updated_codes if updated_codes else None,
            "errors": errors if errors else None,
            "timingSeconds": round(elapsed, 2),
        }
        
        return result
        
    except Exception as e:
        return {
            "success": False,
            "message": f"파일 처리 중 오류 발생: {str(e)}",
            "updatedCount": 0,
            "errorCount": 0,
            "timingSeconds": round(time.time() - start_time, 2),
        }
