# GRPO Network Training Data Collection Pipeline

네트워크 엔지니어링 LLM의 GRPO (Group Relative Policy Optimization) 미세조정을 위한 데이터 수집 및 상대 우위(Advantage) 가공 파이프라인입니다.

## 🚀 주요 기능
- **비동기 멀티 랩 주입**: `Asyncio` + `AsyncScrapli`를 사용하여 4~8개의 독립 가상 랩(Containerlab)에 동시 설정 주입 및 결과 수집.
- **규칙 기반 채점 및 상태 판정**: 문법 에러(`SYNTAX_ERROR`), 포맷 에러(`FORMAT_ERROR`), 성공(`SUCCESS`), 무효(`INEFFECTIVE`) 판정 및 점수 부여.
- **GRPO Relative Advantage 계산**: 그룹 내 보상 평균과 표준편차를 기반으로 상대 우위 정규화 ($A_i = \frac{R_i - \bar{R}}{\sigma_R + 1e-8}$).
- **표준 JSONL 저장**: GRPO 학습셋 형식으로 즉시 활용 가능하도록 레코드 저장.
- **`uv` 환경 관리**: 빠르고 가벼운 파이썬 환경 격리.

## 🛠️ 빠른 시작 (Quick Start with uv)

```bash
# 1. 의존성 설치
uv pip install "scrapli<=2024.7.30" asyncssh numpy pydantic openai rich

# 2. 파이프라인 실행 (시뮬레이션 모드)
uv run python run_collection.py --scenarios data/sample_scenarios.json --output data/grpo_dataset.jsonl --labs-config configs/lab_nodes.json --candidate-count 4 --dry-run
```

## 📁 디렉토리 구조
- `.agents/skills/grpo-network-collector/`: 안티그래비티 전용 Skill 문서
- `configs/`:
  - `lab_nodes.json`: Containerlab 인스턴스 접속 정보(호스트, 포트, 인증정보, 플랫폼 등)
- `src/`:
  - `config.py`: 데이터 모델 규격 및 랩 노드 로더 (`load_lab_nodes`)
  - `generator.py`: LLM 후보군 생성기 (Mock 및 OpenAI 호환)
  - `async_executor.py`: Scrapli 비동기 랩 연결 및 명령어 실행기
  - `evaluator.py`: CLI 출력 검증 및 보상 채점기
  - `advantage.py`: GRPO 상대 우위 계산 로직
  - `pipeline.py`: 시나리오 일괄 처리 및 JSONL 스트리밍 저장
- `data/`:
  - `sample_scenarios.json`: STP 기초 시나리오 예제
  - `grpo_dataset.jsonl`: 생성된 최종 GRPO 데이터셋
