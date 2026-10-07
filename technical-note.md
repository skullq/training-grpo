# GRPO Network Training Data Collection & Evaluation Technical Note

본 문서는 네트워크 자동화 도메인에서 **GRPO(Group Relative Policy Optimization)** 기반 LLM 미세조정(Fine-Tuning)을 수행하기 위한 데이터 수집 파이프라인 아키텍처, 비동기 랩 연동, 보상 함수(Reward Function) 설계 및 수학적 정규화 로직을 종합 정리한 기술 문서입니다.

---

## 1. 아키텍처 및 파이프라인 개요

전통적인 PPO(Proximal Policy Optimization)는 Value Network(Critic)를 별도로 훈련해야 하므로 고비용 메모리와 복잡한 네트워크 상태 추정이 필요합니다. 반면 **GRPO**는 Critic 모델을 제거하고, 하나의 프롬프트에 대해 샘플링된 $G$개의 롤아웃(Completions) 그룹 내부 통계량을 사용하여 상대적 우위(Advantage)를 직접 도출합니다.

```
┌────────────────────────────────────────────────────────────────────────┐
│                        1. 프롬프트 투입 (40개 시나리오)                       │
│    (Task Description, Current Topology State, Target Node, Target VLAN)│
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│                    2. LLM Generator (다양성 샘플링)                     │
│       (GPT-4o / Claude 3.5 / Llama-3-8B with Temperature = 0.8)        │
│       - G=4~5개 후보 Action (<think> 추론 및 <commands> CLI 생성)         │
│       - 최적해(4096), 대안(root primary), 문법 에러(5000), 형식 에러 분산     │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│             3. 병렬 가상 랩 주입 (Asyncio + Scrapli AsyncSSH)             │
│        - 4~8개 독립 Containerlab 인스턴스에 비동기 병렬 접속 (Port 2201~) │
│        - CLI 설정 동시 주입 후 RSTP/Rapid-PVST 3초 수렴 대기              │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│                     4. 결과 수집 및 규칙 기반 채점                       │
│        - show spanning-tree vlan X 출력 및 문법 에러 로그 분석          │
│        - 4단계 보상: SUCCESS(+200), INEFFECTIVE(0), SYNTAX(-150), FORMAT(-200)│
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│                   5. GRPO Relative Advantage 계산                      │
│        - A_i = (R_i - mean(R)) / (std(R) + 1e-8)                      │
│        - 분산(std) = 0 일 때 0.0 클램핑 (그래디언트 폭주 방지)           │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│                    6. 최종 학습용 데이터셋 저장 (JSONL)                   │
│           {"scenario_id": ..., "prompt": ..., "group_outputs": [...]}   │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 2. 세부 단계별 엔지니어링 분석

### 1단계: 프롬프트 투입 및 시나리오 구조화
- 네트워크 설정은 단일 명령어로 끝나지 않으며, 현재 토폴로지 상태에 의존적입니다.
- 따라서 프롬프트는 단순 명령(`SW1을 루트로 변경`)이 아닌 **현재 상태(`현재 SW3가 루트`)**, **대상 스위치(`SW1`)**, **대상 VLAN**을 포함하여 모델이 상태 변화 경로를 올바르게 추론하도록 유도합니다.

### 2단계: Generator 탐색(Exploration) 다양성 확보
- GRPO 학습이 효과를 보려면 그룹 내에 **고득점(정답)**과 **저득점(오답/문법에러)**이 고루 섞여야 합니다.
- `temperature=0.8` 이상을 적용하여 정답 접근법(매크로 명령 vs 수동 우선순위), 문법 오류(비인가 파라미터), 포맷 미준수(설명 텍스트만 출력)를 고루 생성합니다.

### 3단계: 병렬 랩 주입 (Containerlab + Scrapli)
- **독립 포트 격리**: 4~8개의 컨테이너에 각각 포트(`2201`, `2202`, `2203` 등)를 할당하여 동시 주입 시 상호 간섭이 없습니다.
- **AsyncScrapli 드라이버**: `asyncssh` 기반의 비동기 세션을 생성하여 수초 내에 8개 노드의 설정 주입을 병렬 완료합니다.

### 4단계: 수렴 시간 및 보상 채점 (중요 주의사항)
- **⚠️ STP 수렴 시간 경고**: 레거시 802.1D Spanning-Tree는 Listening(15s) + Learning(15s) = 최소 30~50초의 포워딩 지연이 필요합니다.
- 따라서 3초 뒤 `show spanning-tree`로 즉시 결과를 수집하려면 장비 환경이 반드시 **Rapid-PVST+ (`spanning-tree mode rapid-pvst`)** 또는 **RSTP(802.1w)** 여야 합니다 (Proposal-Agreement 메커니즘으로 1초 미만 즉시 수렴).

### 5단계: GRPO Relative Advantage 수식 및 엣지 케이스
$$A_i = \frac{R_i - \text{mean}(R)}{\text{std}(R) + \epsilon}$$
- **표준편차 0 예외 처리**: 모델 생성물이 전부 성공(+200)하거나 전부 실패(-150)하여 $\text{std}(R) = 0$이 될 경우, 분모의 $\epsilon(1e-8)$로 인해 상대 점수가 $\pm 10^8$ 단위로 폭증합니다.
- [src/advantage.py](file:///d:/my-code/training-GRPO/src/advantage.py)에서는 `if std_r < eps: advantages = zeros()` 로 클램핑하여 모든 후보의 Advantage를 0.0으로 안전하게 보정합니다.

---

## 3. 보상 매트릭스 (Reward Matrix)

| 상태 (`status`) | 보상 (`raw_reward`) | 판정 조건 | 학습 시 의미 |
| :--- | :---: | :--- | :--- |
| **`SUCCESS`** | **`+200`** | `show spanning-tree`에 `This bridge is the root` 존재 | 정책을 해당 방향으로 강화 (Positive Reinforcement) |
| **`INEFFECTIVE`** | **`0`** | 문법 에러는 없으나 루트 브리지 선출 실패 | 불필요하거나 무의미한 액션 억제 |
| **`SYNTAX_ERROR`** | **`-150`** | `% Invalid input`, `% Incomplete command` 등 장비 오류 | 문법 오류 패턴을 강력하게 배제 |
| **`FORMAT_ERROR`** | **`-200`** | CLI 명령어가 아닌 자연어 대화체만 출력 | 에이전트의 포맷 이탈에 대해 최악의 패널티 부과 |

---

## 4. 학습용 JSONL 데이터셋 규격

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

## 5. `uv` 환경 관리 및 실행 명령어

```bash
# 가상환경 동기화 및 패키지 설치
uv pip install "scrapli<=2024.7.30" asyncssh numpy pydantic openai rich

# 시뮬레이션 모드 (40개 시나리오 일괄 수집 및 검증)
uv run python run_collection.py --scenarios data/sample_scenarios.json --output data/grpo_dataset.jsonl --lab-count 4 --candidate-count 4 --dry-run

# 실제 Containerlab 환경 연결 모드
uv run python run_collection.py --scenarios data/sample_scenarios.json --output data/grpo_dataset.jsonl --lab-count 4 --candidate-count 4 --live
```
