-- PostgreSQL 스키마

-- pgvector 확장 활성화 (벡터 유사도 검색용)
CREATE EXTENSION IF NOT EXISTS vector;

-- ============================================================
-- project 테이블 생성
-- ============================================================
CREATE TABLE IF NOT EXISTS project (
    project_code        VARCHAR(400)    PRIMARY KEY,                                        -- 프로젝트 코드
    project_name        VARCHAR(200)    NOT NULL,                                           -- 프로젝트 명
    grade_code          VARCHAR(10),                                                        -- 등급
    sap_phase           VARCHAR(100)    CHECK(sap_phase IN (
                            'Pre-Con Deployment Approval',
                            'Contract Approval Request',
                            'Execution Plan Approval'
                        )),                                                                 -- 품의단계
    sales_dept_code     VARCHAR(100),                                                       -- 실행부서
    project_from_date   DATE,                                                               -- 프로젝트시작일 (yyyy-mm-dd)
    contract_account    VARCHAR(400),                                                       -- 고객사 (Contract Account)
    industry_detail     VARCHAR(30),                                                        -- 업종상세
    business_type       VARCHAR(30)     CHECK(business_type IN ('유지보수', '신규', '지원')), -- 사업유형
    summary             TEXT,                                                                -- 사업개요
    methodology_value   VARCHAR(30),                                                        -- 방법론
    embedding           vector(1024),                                                       -- BGE-M3 임베딩 벡터
    created_at          TIMESTAMP       DEFAULT CURRENT_TIMESTAMP,                          -- 생성일시
    updated_at          TIMESTAMP       DEFAULT CURRENT_TIMESTAMP                           -- 수정일시
);

-- 인덱스 생성
CREATE INDEX IF NOT EXISTS idx_project_grade_code       ON project(grade_code);
CREATE INDEX IF NOT EXISTS idx_project_sap_phase        ON project(sap_phase);
CREATE INDEX IF NOT EXISTS idx_project_sales_dept_code  ON project(sales_dept_code);
CREATE INDEX IF NOT EXISTS idx_project_industry_detail  ON project(industry_detail);
CREATE INDEX IF NOT EXISTS idx_project_business_type    ON project(business_type);
CREATE INDEX IF NOT EXISTS idx_project_contract_account ON project(contract_account);
CREATE INDEX IF NOT EXISTS idx_project_project_name     ON project(project_name);

-- 업데이트 시간 자동 갱신 트리거 함수
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

-- 트리거 생성
DROP TRIGGER IF EXISTS update_project_updated_at ON project;
CREATE TRIGGER update_project_updated_at
    BEFORE UPDATE ON project
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();
