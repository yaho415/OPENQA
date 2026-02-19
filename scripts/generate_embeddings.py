#!/usr/bin/env python3
"""
기존 cases 데이터를 벡터화하는 스크립트 (BGE-M3 모델, CPU 최적화)
사용법: python scripts/generate_embeddings.py
"""

import asyncio
import os
import sys
import time

# 프로젝트 루트를 sys.path에 추가
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

load_dotenv()

from src.database.db import get_database
from src.vector_embedder import VectorEmbedder, get_vector_embedder


async def generate_embeddings():
    """기존 사례 데이터를 벡터화"""
    print("BGE-M3 벡터 임베딩 생성 시작...\n")
    print("CPU 모드로 실행됩니다.\n")

    db = get_database()
    embedder = get_vector_embedder()

    try:
        print(f"모델: {embedder.get_model_name()}")
        print(f"차원: {embedder.get_dimension()}차원\n")

        # 1. 임베딩 상태 확인
        status = db.get_embedding_status()
        print("현재 상태:")
        print(f"   전체 사례: {status['total']}개")
        print(f"   임베딩 있음: {status['with_embedding']}개")
        print(f"   임베딩 없음: {status['without_embedding']}개\n")

        if status["without_embedding"] == 0:
            print("모든 사례가 이미 벡터화되어 있습니다!")
            return

        # 2. 임베딩이 없는 사례 가져오기
        cases_without_embedding = db.get_cases_without_embedding()
        print(f"\n{len(cases_without_embedding)}개 사례를 벡터화합니다...\n")

        # 3. 각 사례를 벡터화
        success_count = 0
        error_count = 0
        start_time = time.time()

        for i, case_item in enumerate(cases_without_embedding):
            try:
                # 임베딩용 텍스트 생성
                embedding_text = VectorEmbedder.create_embedding_text(case_item)

                # 벡터 생성 (async)
                progress = f"[{i + 1}/{len(cases_without_embedding)}]"
                print(f"{progress} {case_item.project_name} 벡터화 중...")

                embedding = await embedder.embed(embedding_text)

                # 데이터베이스에 저장
                db.update_case_embedding(case_item.id, embedding)

                success_count += 1
                elapsed = f"{time.time() - start_time:.1f}"
                print(f"   완료 ({len(embedding)}차원, 경과: {elapsed}초)\n")

            except Exception as e:
                error_count += 1
                print(f"   오류: {e}\n")

        # 4. 최종 상태 확인
        total_time = f"{time.time() - start_time:.1f}"
        print("\n" + "=" * 80)
        print("벡터화 완료:")
        print(f"   성공: {success_count}개")
        print(f"   실패: {error_count}개")
        print(f"   총 소요 시간: {total_time}초")
        if success_count > 0:
            avg_time = float(total_time) / success_count
            print(f"   평균 처리 시간: {avg_time:.2f}초/개")

        final_status = db.get_embedding_status()
        print(f"\n   전체 사례: {final_status['total']}개")
        print(f"   임베딩 있음: {final_status['with_embedding']}개")
        print(f"   임베딩 없음: {final_status['without_embedding']}개")
        print("=" * 80 + "\n")

        db.close()
        await embedder.close()

    except Exception as e:
        print(f"오류 발생: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(generate_embeddings())
