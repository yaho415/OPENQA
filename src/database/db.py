"""
PostgreSQL 데이터베이스 연결 및 관리 클래스
"""

import json
import os
from pathlib import Path
from typing import List, Optional, Tuple

import psycopg2
from psycopg2 import pool
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

from src.types.case import Project

load_dotenv()


class DatabaseManager:
    """PostgreSQL 데이터베이스 연결 클래스"""

    def __init__(self):
        self._pool: Optional[pool.SimpleConnectionPool] = None
        self.db_name = os.getenv("DB_NAME", "mcp_cases")
        self._initialize_pool()
        self._initialize_schema()

    def _initialize_pool(self):
        """커넥션 풀 초기화"""
        try:
            self._pool = pool.SimpleConnectionPool(
                minconn=1,
                maxconn=20,
                host=os.getenv("DB_HOST", "localhost"),
                port=int(os.getenv("DB_PORT", "5432")),
                database=self.db_name,
                user=os.getenv("DB_USER", "postgres"),
                password=os.getenv("DB_PASSWORD", ""),
                connect_timeout=5,
            )
        except Exception as e:
            print(f"❌ 데이터베이스 연결 풀 생성 실패: {e}")
            raise

    def _get_conn(self):
        """커넥션 풀에서 커넥션 가져오기"""
        if self._pool is None:
            raise RuntimeError("데이터베이스 연결 풀이 초기화되지 않았습니다.")
        return self._pool.getconn()

    def _put_conn(self, conn):
        """커넥션을 풀에 반환"""
        if self._pool is not None:
            self._pool.putconn(conn)

    def _initialize_schema(self):
        """데이터베이스 스키마 초기화"""
        schema_path = Path(__file__).parent / "schema.sql"
        try:
            if schema_path.exists():
                schema = schema_path.read_text(encoding="utf-8")
            else:
                schema = self._get_fallback_schema()

            conn = self._get_conn()
            try:
                with conn.cursor() as cur:
                    cur.execute(schema)
                conn.commit()
                print("✅ 데이터베이스 스키마가 초기화되었습니다.")
            finally:
                self._put_conn(conn)
        except Exception as e:
            print(f"⚠️ 스키마 초기화 중 오류: {e}")

    @staticmethod
    def _get_fallback_schema() -> str:
        """스키마 파일이 없을 때 사용할 fallback 스키마"""
        return """
        CREATE EXTENSION IF NOT EXISTS vector;

        CREATE TABLE IF NOT EXISTS project (
            project_code        VARCHAR(400)    PRIMARY KEY,
            project_name        VARCHAR(200)    NOT NULL,
            grade_code          VARCHAR(10),
            sap_phase           VARCHAR(20)     CHECK(sap_phase IN ('S', 'A', 'B', 'C')),
            sales_dept_code     VARCHAR(100),
            project_from_date   DATE,
            contract_account    VARCHAR(400),
            industry_detail     VARCHAR(30),
            business_type       VARCHAR(30)     CHECK(business_type IN ('유지보수', '신규', '지원')),
            summary             VARCHAR(400),
            methodology_value   VARCHAR(30),
            embedding           vector(1024),
            created_at          TIMESTAMP       DEFAULT CURRENT_TIMESTAMP,
            updated_at          TIMESTAMP       DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_project_grade_code       ON project(grade_code);
        CREATE INDEX IF NOT EXISTS idx_project_sap_phase        ON project(sap_phase);
        CREATE INDEX IF NOT EXISTS idx_project_sales_dept_code  ON project(sales_dept_code);
        CREATE INDEX IF NOT EXISTS idx_project_industry_detail  ON project(industry_detail);
        CREATE INDEX IF NOT EXISTS idx_project_business_type    ON project(business_type);
        CREATE INDEX IF NOT EXISTS idx_project_contract_account ON project(contract_account);
        CREATE INDEX IF NOT EXISTS idx_project_name             ON project(project_name);

        CREATE OR REPLACE FUNCTION update_updated_at_column()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = CURRENT_TIMESTAMP;
            RETURN NEW;
        END;
        $$ language 'plpgsql';

        DROP TRIGGER IF EXISTS update_project_updated_at ON project;
        CREATE TRIGGER update_project_updated_at
            BEFORE UPDATE ON project
            FOR EACH ROW
            EXECUTE FUNCTION update_updated_at_column();
        """

    @staticmethod
    def _row_to_project(row: dict) -> Project:
        """데이터베이스 행을 Project 객체로 변환"""
        return Project(
            project_code=row["project_code"],
            project_name=row["project_name"],
            grade_code=row.get("grade_code"),
            sap_phase=row.get("sap_phase"),
            sales_dept_code=row.get("sales_dept_code"),
            project_from_date=str(row["project_from_date"]) if row.get("project_from_date") else None,
            contract_account=row.get("contract_account"),
            industry_detail=row.get("industry_detail"),
            business_type=row.get("business_type"),
            summary=row.get("summary"),
            methodology_value=row.get("methodology_value"),
        )

    # ──────────────────────────────────────────────────────────
    # CRUD 연산
    # ──────────────────────────────────────────────────────────

    def get_all_projects(self) -> List[Project]:
        """모든 프로젝트 조회"""
        conn = self._get_conn()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT * FROM project ORDER BY created_at DESC")
                rows = cur.fetchall()
            return [self._row_to_project(row) for row in rows]
        finally:
            self._put_conn(conn)

    def get_project_by_code(self, project_code: str) -> Optional[Project]:
        """프로젝트 코드로 조회"""
        conn = self._get_conn()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT * FROM project WHERE project_code = %s", (project_code,))
                row = cur.fetchone()
            return self._row_to_project(row) if row else None
        finally:
            self._put_conn(conn)

    def insert_project(self, item: Project) -> None:
        """프로젝트 추가"""
        conn = self._get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO project (
                        project_code, project_name, grade_code, sap_phase,
                        sales_dept_code, project_from_date, contract_account,
                        industry_detail, business_type, summary, methodology_value
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                    (
                        item.project_code,
                        item.project_name,
                        item.grade_code,
                        item.sap_phase,
                        item.sales_dept_code,
                        item.project_from_date,
                        item.contract_account,
                        item.industry_detail,
                        item.business_type,
                        item.summary,
                        item.methodology_value,
                    ),
                )
            conn.commit()
        finally:
            self._put_conn(conn)

    def update_project(self, item: Project) -> None:
        """프로젝트 업데이트 (updated_at 자동 갱신)"""
        conn = self._get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """UPDATE project SET
                        project_name = %s, grade_code = %s, sap_phase = %s,
                        sales_dept_code = %s, project_from_date = %s,
                        contract_account = %s, industry_detail = %s,
                        business_type = %s, summary = %s, methodology_value = %s,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE project_code = %s""",
                    (
                        item.project_name,
                        item.grade_code,
                        item.sap_phase,
                        item.sales_dept_code,
                        item.project_from_date,
                        item.contract_account,
                        item.industry_detail,
                        item.business_type,
                        item.summary,
                        item.methodology_value,
                        item.project_code,
                    ),
                )
            conn.commit()
        finally:
            self._put_conn(conn)

    def delete_project(self, project_code: str) -> None:
        """프로젝트 삭제"""
        conn = self._get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM project WHERE project_code = %s", (project_code,))
            conn.commit()
        finally:
            self._put_conn(conn)

    # ──────────────────────────────────────────────────────────
    # 필터링 조회
    # ──────────────────────────────────────────────────────────

    def get_projects_by_industry(self, industry: str) -> List[Project]:
        """업종별 프로젝트 조회"""
        conn = self._get_conn()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    "SELECT * FROM project WHERE industry_detail = %s ORDER BY created_at DESC",
                    (industry,),
                )
                rows = cur.fetchall()
            return [self._row_to_project(row) for row in rows]
        finally:
            self._put_conn(conn)

    def get_projects_by_grade(self, grade: str) -> List[Project]:
        """등급별 프로젝트 조회"""
        conn = self._get_conn()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    "SELECT * FROM project WHERE grade_code = %s ORDER BY created_at DESC",
                    (grade,),
                )
                rows = cur.fetchall()
            return [self._row_to_project(row) for row in rows]
        finally:
            self._put_conn(conn)

    def search_projects_by_keyword(self, keyword: str) -> List[Project]:
        """키워드로 프로젝트 검색"""
        search_term = f"%{keyword.lower()}%"
        conn = self._get_conn()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """SELECT * FROM project
                    WHERE LOWER(project_name) LIKE %s
                       OR LOWER(COALESCE(summary, '')) LIKE %s
                       OR LOWER(COALESCE(sales_dept_code, '')) LIKE %s
                       OR LOWER(COALESCE(industry_detail, '')) LIKE %s
                       OR LOWER(COALESCE(contract_account, '')) LIKE %s
                       OR LOWER(COALESCE(business_type, '')) LIKE %s
                    ORDER BY created_at DESC""",
                    (search_term, search_term, search_term, search_term, search_term, search_term),
                )
                rows = cur.fetchall()
            return [self._row_to_project(row) for row in rows]
        finally:
            self._put_conn(conn)

    # ──────────────────────────────────────────────────────────
    # 벡터 임베딩 관련
    # ──────────────────────────────────────────────────────────

    def get_embedding_status(self) -> dict:
        """임베딩 상태 확인"""
        conn = self._get_conn()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT
                        COUNT(*) as total,
                        COUNT(embedding) as with_embedding,
                        COUNT(*) - COUNT(embedding) as without_embedding
                    FROM project
                """)
                row = cur.fetchone()
            return {
                "total": int(row["total"]),
                "with_embedding": int(row["with_embedding"]),
                "without_embedding": int(row["without_embedding"]),
            }
        finally:
            self._put_conn(conn)

    def get_projects_without_embedding(self) -> List[Project]:
        """임베딩이 없는 프로젝트 가져오기"""
        conn = self._get_conn()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    "SELECT * FROM project WHERE embedding IS NULL ORDER BY created_at DESC"
                )
                rows = cur.fetchall()
            return [self._row_to_project(row) for row in rows]
        finally:
            self._put_conn(conn)

    def update_project_embedding(self, project_code: str, embedding: List[float]) -> None:
        """프로젝트에 임베딩 업데이트"""
        embedding_str = "[" + ",".join(str(v) for v in embedding) + "]"
        conn = self._get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE project SET embedding = %s::vector WHERE project_code = %s",
                    (embedding_str, project_code),
                )
            conn.commit()
        finally:
            self._put_conn(conn)

    def search_similar_projects_by_vector(
        self,
        query_embedding: List[float],
        limit: int = 5,
        threshold: Optional[float] = None,
    ) -> List[Tuple[Project, float]]:
        """
        벡터 유사도 검색 (코사인 유사도 사용)

        Args:
            query_embedding: 검색할 벡터 (1024차원)
            limit: 반환할 최대 결과 수
            threshold: 최소 유사도 임계값 (0-1, 선택적)

        Returns:
            (Project, similarity) 튜플 리스트
        """
        embedding_str = "[" + ",".join(str(v) for v in query_embedding) + "]"

        query = """
            SELECT
                project_code, project_name, grade_code, sap_phase,
                sales_dept_code, project_from_date, contract_account,
                industry_detail, business_type, summary, methodology_value,
                1 - (embedding <=> %s::vector) / 2.0 as similarity
            FROM project
            WHERE embedding IS NOT NULL
        """
        params: list = [embedding_str]

        if threshold is not None:
            query += " AND (1 - (embedding <=> %s::vector) / 2.0) >= %s"
            params.extend([embedding_str, threshold])

        query += " ORDER BY embedding <=> %s::vector LIMIT %s"
        params.extend([embedding_str, limit])

        conn = self._get_conn()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(query, params)
                rows = cur.fetchall()
            return [
                (self._row_to_project(row), float(row["similarity"]))
                for row in rows
            ]
        finally:
            self._put_conn(conn)

    # ──────────────────────────────────────────────────────────
    # 하위 호환 메서드 (기존 코드 호환)
    # ──────────────────────────────────────────────────────────

    def get_all_cases(self) -> List[Project]:
        return self.get_all_projects()

    def get_case_by_id(self, case_id: str) -> Optional[Project]:
        return self.get_project_by_code(case_id)

    def insert_case(self, item: Project) -> None:
        return self.insert_project(item)

    def update_case(self, item: Project) -> None:
        return self.update_project(item)

    def update_case_embedding(self, case_id: str, embedding: List[float]) -> None:
        return self.update_project_embedding(case_id, embedding)

    def search_similar_cases_by_vector(
        self, query_embedding: List[float], limit: int = 5, threshold: Optional[float] = None
    ) -> List[Tuple[Project, float]]:
        return self.search_similar_projects_by_vector(query_embedding, limit, threshold)

    def search_cases_by_keyword(self, keyword: str) -> List[Project]:
        return self.search_projects_by_keyword(keyword)

    def get_cases_by_industry(self, industry: str) -> List[Project]:
        return self.get_projects_by_industry(industry)

    def get_cases_by_grade(self, grade: str) -> List[Project]:
        return self.get_projects_by_grade(grade)

    # ──────────────────────────────────────────────────────────
    # 연결 관리
    # ──────────────────────────────────────────────────────────

    def close(self):
        """데이터베이스 연결 종료"""
        if self._pool is not None:
            self._pool.closeall()
            self._pool = None


# ──────────────────────────────────────────────────────────
# 싱글톤
# ──────────────────────────────────────────────────────────

_db_instance: Optional[DatabaseManager] = None


def get_database() -> DatabaseManager:
    """데이터베이스 싱글톤 인스턴스 반환"""
    global _db_instance
    if _db_instance is None:
        _db_instance = DatabaseManager()
    return _db_instance
