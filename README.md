# GRPO Network Training Data Collection Pipeline

네트워크 엔지니어링 LLM의 GRPO (Group Relative Policy Optimization) 미세조정을 위한 데이터 수집 및 상대 우위(Advantage) 가공 파이프라인입니다.

## 🚀 주요 기능
- **비동기 멀티 랩 주입**: `Asyncio` + `AsyncScrapli`를 사용하여 4~8개의 독립 가상 랩(Containerlab)에 동시 설정 주입 및 결과 수집.
- **규칙 기반 채점 및 상태 판정**: 문법 에러(`SYNTAX_ERROR`), 포맷 에러(`FORMAT_ERROR`), 성공(`SUCCESS`), 무효(`INEFFECTIVE`) 판정 및 점수 부여.
- **GRPO Relative Advantage 계산**: 그룹 내 보상 평균과 표준편차를 기반으로 상대 우위 정규화 ($A_i = \frac{R_i - \bar{R}}{\sigma_R + 1e-8}$).
- **표준 JSONL 저장**: GRPO 학습셋 형식으로 즉시 활용 가능하도록 레코드 저장.
- **`uv` 환경 관리**: 빠르고 가벼운 파이썬 환경 격리.

## 📖 GPU 서버 LoRA 파인튜닝 가이드
- **[공식 훈련 가이드 문서 (docs/GRPO_LORA_TRAINING_GUIDE.md)](docs/GRPO_LORA_TRAINING_GUIDE.md)**: 3B 모델(Qwen2.5-3B, Llama-3.2-3B) LoRA 하이퍼파라미터 권장값, TRL 학습 스크립트 예시, 데이터셋 구조 분석 수록.

## 🛠️ 빠른 시작 (Quick Start)

```bash
# 1. 단위 랩 (Unit Test 3-node) 모드 실행 (120 시나리오)
uv run python run_collection.py --topology unit --candidate-count 4 --dry-run

# 2. 다계층 통합 랩 (Multi-tier Redundant) 모드 실행 (150 시나리오, 권장)
uv run python run_collection.py --topology multitier --candidate-count 4 --dry-run
```

## 📁 디렉토리 구조
- `docs/`:
  - `GRPO_LORA_TRAINING_GUIDE.md`: GPU 서버 파인튜닝 가이드 및 기술 아키텍처 문서
- `configs/`:
  - `lab_nodes_8.json`: 3-Node 단위 랩 8개 인스턴스 접속 정보
  - `lab_nodes_integration.json`: 6대 다계층 통합 랩 접속 정보
- `labs/`:
  - `iol-8labs-24sw.clab.yml`: 24대 Cisco IOL 컨테이너랩 토폴로지
  - `iol-multitier-integration.clab.yml`: Core-Dist-Access 이중화 메시 토폴로지
- `src/`:
  - `generator.py`: 4단계 CoT 추론 지원 액션 생성기
  - `async_executor.py`: 동적 수렴 감지(Dynamic Convergence Polling) Scrapli 비동기 주입기
  - `evaluator.py`: L2 Trunk / MSTP / Port-Channel 정밀 CLI 채점기
  - `pipeline.py`: GRPO 품질 게이트(sigma > 0) 및 데이터 수집 파이프라인
- `data/`:
  - `grpo_scenario_multitier_150.json`: 150개 최종 시나리오
  - `grpo_dataset_multitier_150.jsonl`: 3B LoRA 학습용 최종 데이터셋

