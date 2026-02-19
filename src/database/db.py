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

from src.types.case import Case

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

        CREATE TABLE IF NOT EXISTS cases (
            id VARCHAR(50) PRIMARY KEY,
            project_name TEXT NOT NULL,
            grade VARCHAR(1) NOT NULL CHECK(grade IN ('A', 'B', 'C')),
            department TEXT NOT NULL,
            industry TEXT NOT NULL,
            business_overview TEXT NOT NULL,
            keywords JSONB NOT NULL,
            category TEXT,
            tags JSONB,
            embedding vector(1024),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_industry ON cases(industry);
        CREATE INDEX IF NOT EXISTS idx_grade ON cases(grade);
        CREATE INDEX IF NOT EXISTS idx_department ON cases(department);
        CREATE INDEX IF NOT EXISTS idx_project_name ON cases(project_name);

        CREATE OR REPLACE FUNCTION update_updated_at_column()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = CURRENT_TIMESTAMP;
            RETURN NEW;
        END;
        $$ language 'plpgsql';

        DROP TRIGGER IF EXISTS update_cases_updated_at ON cases;
        CREATE TRIGGER update_cases_updated_at
            BEFORE UPDATE ON cases
            FOR EACH ROW
            EXECUTE FUNCTION update_updated_at_column();
        """

    @staticmethod
    def _row_to_case(row: dict) -> Case:
        """데이터베이스 행을 Case 객체로 변환"""
        keywords = row.get("keywords", [])
        if isinstance(keywords, str):
            keywords = json.loads(keywords)

        tags = row.get("tags")
        if isinstance(tags, str):
            tags = json.loads(tags)

        return Case(
            id=row["id"],
            project_name=row["project_name"],
            grade=row["grade"],
            department=row["department"],
            industry=row["industry"],
            business_overview=row["business_overview"],
            keywords=keywords if isinstance(keywords, list) else [],
            category=row.get("category") or None,
            tags=tags if isinstance(tags, list) else None,
        )

    # ──────────────────────────────────────────────────────────
    # CRUD 연산
    # ──────────────────────────────────────────────────────────

    def get_all_cases(self) -> List[Case]:
        """모든 사례 조회"""
        conn = self._get_conn()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT * FROM cases ORDER BY created_at DESC")
                rows = cur.fetchall()
            return [self._row_to_case(row) for row in rows]
        finally:
            self._put_conn(conn)

    def get_case_by_id(self, case_id: str) -> Optional[Case]:
        """ID로 사례 조회"""
        conn = self._get_conn()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT * FROM cases WHERE id = %s", (case_id,))
                row = cur.fetchone()
            return self._row_to_case(row) if row else None
        finally:
            self._put_conn(conn)

    def insert_case(self, case_item: Case) -> None:
        """사례 추가"""
        conn = self._get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO cases (
                        id, project_name, grade, department, industry,
                        business_overview, keywords, category, tags
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                    (
                        case_item.id,
                        case_item.project_name,
                        case_item.grade,
                        case_item.department,
                        case_item.industry,
                        case_item.business_overview,
                        json.dumps(case_item.keywords, ensure_ascii=False),
                        case_item.category,
                        json.dumps(case_item.tags, ensure_ascii=False) if case_item.tags else None,
                    ),
                )
            conn.commit()
        finally:
            self._put_conn(conn)

    def update_case(self, case_item: Case) -> None:
        """사례 업데이트"""
        conn = self._get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """UPDATE cases SET
                        project_name = %s, grade = %s, department = %s,
                        industry = %s, business_overview = %s,
                        keywords = %s, category = %s, tags = %s
                    WHERE id = %s""",
                    (
                        case_item.project_name,
                        case_item.grade,
                        case_item.department,
                        case_item.industry,
                        case_item.business_overview,
                        json.dumps(case_item.keywords, ensure_ascii=False),
                        case_item.category,
                        json.dumps(case_item.tags, ensure_ascii=False) if case_item.tags else None,
                        case_item.id,
                    ),
                )
            conn.commit()
        finally:
            self._put_conn(conn)

    def delete_case(self, case_id: str) -> None:
        """사례 삭제"""
        conn = self._get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM cases WHERE id = %s", (case_id,))
            conn.commit()
        finally:
            self._put_conn(conn)

    # ──────────────────────────────────────────────────────────
    # 필터링 조회
    # ──────────────────────────────────────────────────────────

    def get_cases_by_industry(self, industry: str) -> List[Case]:
        """업종별 사례 조회"""
        conn = self._get_conn()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    "SELECT * FROM cases WHERE industry = %s ORDER BY created_at DESC",
                    (industry,),
                )
                rows = cur.fetchall()
            return [self._row_to_case(row) for row in rows]
        finally:
            self._put_conn(conn)

    def get_cases_by_department(self, department: str) -> List[Case]:
        """부서별 사례 조회"""
        conn = self._get_conn()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    "SELECT * FROM cases WHERE department = %s ORDER BY created_at DESC",
                    (department,),
                )
                rows = cur.fetchall()
            return [self._row_to_case(row) for row in rows]
        finally:
            self._put_conn(conn)

    def get_cases_by_grade(self, grade: str) -> List[Case]:
        """등급별 사례 조회"""
        conn = self._get_conn()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    "SELECT * FROM cases WHERE grade = %s ORDER BY created_at DESC",
                    (grade,),
                )
                rows = cur.fetchall()
            return [self._row_to_case(row) for row in rows]
        finally:
            self._put_conn(conn)

    def search_cases_by_keyword(self, keyword: str) -> List[Case]:
        """키워드로 사례 검색"""
        search_term = f"%{keyword.lower()}%"
        conn = self._get_conn()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """SELECT * FROM cases
                    WHERE LOWER(project_name) LIKE %s
                       OR LOWER(business_overview) LIKE %s
                       OR LOWER(department) LIKE %s
                       OR LOWER(industry) LIKE %s
                       OR LOWER(keywords::text) LIKE %s
                    ORDER BY created_at DESC""",
                    (search_term, search_term, search_term, search_term, search_term),
                )
                rows = cur.fetchall()
            return [self._row_to_case(row) for row in rows]
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
                    FROM cases
                """)
                row = cur.fetchone()
            return {
                "total": int(row["total"]),
                "with_embedding": int(row["with_embedding"]),
                "without_embedding": int(row["without_embedding"]),
            }
        finally:
            self._put_conn(conn)

    def get_cases_without_embedding(self) -> List[Case]:
        """임베딩이 없는 사례 가져오기"""
        conn = self._get_conn()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    "SELECT * FROM cases WHERE embedding IS NULL ORDER BY created_at DESC"
                )
                rows = cur.fetchall()
            return [self._row_to_case(row) for row in rows]
        finally:
            self._put_conn(conn)

    def update_case_embedding(self, case_id: str, embedding: List[float]) -> None:
        """사례에 임베딩 업데이트"""
        embedding_str = "[" + ",".join(str(v) for v in embedding) + "]"
        conn = self._get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE cases SET embedding = %s::vector WHERE id = %s",
                    (embedding_str, case_id),
                )
            conn.commit()
        finally:
            self._put_conn(conn)

    def search_similar_cases_by_vector(
        self,
        query_embedding: List[float],
        limit: int = 5,
        threshold: Optional[float] = None,
    ) -> List[Tuple[Case, float]]:
        """
        벡터 유사도 검색 (코사인 유사도 사용)

        Args:
            query_embedding: 검색할 벡터 (1024차원)
            limit: 반환할 최대 결과 수
            threshold: 최소 유사도 임계값 (0-1, 선택적)

        Returns:
            (Case, similarity) 튜플 리스트
        """
        embedding_str = "[" + ",".join(str(v) for v in query_embedding) + "]"

        query = """
            SELECT
                id, project_name, grade, department, industry,
                business_overview, keywords, category, tags,
                1 - (embedding <=> %s::vector) / 2.0 as similarity
            FROM cases
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
                (self._row_to_case(row), float(row["similarity"]))
                for row in rows
            ]
        finally:
            self._put_conn(conn)

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
