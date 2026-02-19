-- PostgreSQL 스키마

-- pgvector 확장 활성화 (벡터 유사도 검색용)
CREATE EXTENSION IF NOT EXISTS vector;

-- cases 테이블 생성
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

-- 인덱스 생성
CREATE INDEX IF NOT EXISTS idx_industry ON cases(industry);
CREATE INDEX IF NOT EXISTS idx_grade ON cases(grade);
CREATE INDEX IF NOT EXISTS idx_department ON cases(department);
CREATE INDEX IF NOT EXISTS idx_project_name ON cases(project_name);

-- 업데이트 시간 자동 갱신 트리거 함수
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

-- 트리거 생성
DROP TRIGGER IF EXISTS update_cases_updated_at ON cases;
CREATE TRIGGER update_cases_updated_at
    BEFORE UPDATE ON cases
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();
