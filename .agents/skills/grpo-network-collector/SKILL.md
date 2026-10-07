---
name: grpo-network-collector
description: >-
  Pipeline guide and execution skill for GRPO (Group Relative Policy Optimization) training data collection.
  Use when generating network configuration actions, running parallel Asyncio+Scrapli injections on Containerlab,
  evaluating CLI output rewards, calculating group relative advantages, and formatting JSONL datasets.
---

# GRPO Network Data Collection & Processing Skill

이 스킬은 네트워크 자동화 시나리오(Spanning-Tree 등)를 대상으로 **GRPO (Group Relative Policy Optimization)** 모델 학습용 데이터셋을 생성하고, 비동기 가상 랩 주입 및 상대 우위(Advantage) 점수를 계산하여 JSONL 규격으로 가공하는 워크플로우를 제공합니다.

---

## 1. 데이터 수집 단계별 아키텍처 및 검토 (Pipeline Review)

| 단계 | 파이프라인 | 주요 동작 | 핵심 검토 및 엔지니어링 주의점 |
| :--- | :--- | :--- | :--- |
| **1단계** | **프롬프트 투입** | 40개 기초 시나리오 요구사항 전달 | - 네트워크 상태(Current State), 목표(Goal), 대상 장비(Target Node) 명시<br>- `<think>` 추론과 `<commands>` 액션 분리 유도 |
| **2단계** | **LLM Generator** | GPT-4o / Claude / Llama-3로 4~5개 후보 Action 생성 | - `temperature=0.7~0.9`로 설정하여 정답, 대안, 문법 에러, 자연어 응답 등 다양성(Exploration) 확보 |
| **3단계** | **병렬 랩 주입** | `Asyncio + Scrapli`로 4~8개 독립 가상 랩(Containerlab) 동시 연결 | - `AsyncScrapli` (asyncssh 드라이버) 활용<br>- 독립 컨테이너 포트 매핑으로 상호 간섭 배제 |
| **4단계** | **결과 수집 및 채점** | 3초 후 `show spanning-tree` 수집 및 보상 산정 | ⚠️ **STP 수렴 주의**: 표준 802.1D STP는 기본 포워딩 지연이 30~50초 소요되므로, 3초 검증을 위해서는 반드시 **Rapid-PVST+** 또는 **RSTP** 모드 필수!<br>- 성공: +200, 문법오류: -150, 형식오류: -200, 무효: 0 |
| **5단계** | **상대 점수 계산** | 그룹 내 $A_i = \frac{R_i - \bar{R}}{\sigma_R + 1e-8}$ 계산 | - 모든 답변의 보상이 같을 때 ($\sigma=0$) $A_i = 0.0$ 클램핑 처리로 분모 발산 방지 |
| **6단계** | **데이터셋 저장** | 단일 JSONL 파일로 그룹화 저장 | - 각 줄마다 `scenario_id`, `prompt`, `group_outputs` 구조로 영구 보관 |

---

## 2. uv 환경 관리 및 실행 가이드

본 프로젝트는 **`uv`**를 사용하여 초고속 가상환경과 의존성을 관리합니다.

### 의존성 설치
```bash
# 가상환경 생성 및 패키지 동기화
uv sync
# 또는 개별 설치 시
uv pip install "scrapli<=2024.7.30" asyncssh numpy pydantic openai rich
```

### 데이터 수집 파이프라인 실행
```bash
# 시뮬레이션 모드 (Containerlab 장비 없이 로직 검증)
uv run python run_collection.py --scenarios data/sample_scenarios.json --output data/grpo_dataset.jsonl --lab-count 4 --candidate-count 4 --dry-run

# 실제 Containerlab 연결 모드 (Live)
uv run python run_collection.py --scenarios data/sample_scenarios.json --output data/grpo_dataset.jsonl --lab-count 4 --candidate-count 4 --live
```

---

## 3. 학습용 JSONL 데이터셋 규격

저장되는 JSONL 파일은 1줄당 1개의 시나리오 그룹 단위로 저장됩니다:

```json
{
  "scenario_id": "STP_ROOT_SETTING_01",
  "prompt": "SW1을 Root Bridge로 설정하세요. (현재 상태: SW3가 Root)",
  "group_outputs": [
    {
      "output": "spanning-tree vlan 1 priority 4096",
      "raw_reward": 200.0,
      "relative_advantage": 1.0,
      "status": "SUCCESS"
    },
    {
      "output": "spanning-tree vlan 1 root primary",
      "raw_reward": 200.0,
      "relative_advantage": 1.0,
      "status": "SUCCESS"
    },
    {
      "output": "spanning-tree vlan 1 priority 5000",
      "raw_reward": -150.0,
      "relative_advantage": -0.86,
      "status": "SYNTAX_ERROR"
    },
    {
      "output": "SW1을 루트 브리지로 변경했습니다.",
      "raw_reward": -200.0,
      "relative_advantage": -1.13,
      "status": "FORMAT_ERROR"
    }
  ]
}
```

---

## 4. 핵심 모듈 링크

- 엔트리포인트: [run_collection.py](file:///d:/my-code/training-GRPO/run_collection.py)
- Pydantic 데이터 모델: [src/config.py](file:///d:/my-code/training-GRPO/src/config.py)
- 비동기 Scrapli 주입기: [src/async_executor.py](file:///d:/my-code/training-GRPO/src/async_executor.py)
- 보상 및 상태 평가기: [src/evaluator.py](file:///d:/my-code/training-GRPO/src/evaluator.py)
- GRPO Advantage 연산기: [src/advantage.py](file:///d:/my-code/training-GRPO/src/advantage.py)
- 전체 파이프라인: [src/pipeline.py](file:///d:/my-code/training-GRPO/src/pipeline.py)
- 수학 및 아키텍처 상세 문서: [grpo_reward_design.md](./references/grpo_reward_design.md)
