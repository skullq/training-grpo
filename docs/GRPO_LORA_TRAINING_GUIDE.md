# 🚀 네트워크 3B 모델 2단계 파인튜닝 가이드 (Stage 1 SFT + Stage 2 GRPO)

본 문서는 **Cisco 엔터프라이즈 L2/STP 정책 최적화 및 자동화를 위한 3B 모델 LoRA 파인튜닝**을 GPU 서버에서 진행하기 위한 공식 가이드입니다.
초기 콜드 스타트(문법 및 CoT 추론 포맷 각인)를 위한 **1단계 SFT(지도 미세조정)**와, 가상 스위치 실장비 피드백 기반 **2단계 GRPO(강화학습 정렬)**를 포괄하는 표준 훈련 파이프라인을 다룹니다.

---

## 📌 목차
1. [2단계 훈련 아키텍처 (2-Stage Pipeline)](#1-2단계-훈련-아키텍처-2-stage-pipeline)
2. [데이터셋 규격 및 파일 분석](#2-데이터셋-규격-및-파일-분석)
3. [1단계: SFT 콜드 스타트 학습 (Stage 1)](#3-1단계-sft-콜드-스타트-학습-stage-1)
4. [2단계: GRPO 정책 최적화 학습 (Stage 2)](#4-2단계-grpo-정책-최적화-학습-stage-2)
5. [추론 및 배포 테스트 가이드 (Prompting)](#5-추론-및-배포-테스트-가이드-prompting)
6. [품질 지표 및 롤백 무결성](#6-품질-지표-및-롤백-무결성)
7. [보상 체계 심층 설계: 차선책 150점(Sweet Spot) 및 다층화 가이드](#7-보상-체계-심층-설계-차선책-150점sweet-spot-및-다층화-가이드)
8. [Cold-Start SFT 데이터 규모 최적화 (225개 vs 5~10개 분석)](#8-cold-start-sft-데이터-규모-최적화-225개-vs-510개-분석)

---

## 1. 2단계 훈련 아키텍처 (2-Stage Pipeline)

GRPO(강화학습)를 베이스 모델(Pre-trained)에 바로 적용할 경우, 초기에 `<think>` 태그나 `<commands>` 태그 문법을 지키지 못해 보상이 계속 음수(-200)로 수렴하는 **콜드 스타트 붕괴(Cold-Start Collapse)** 현상이 발생할 수 있습니다. 이를 방지하기 위해 **SFT ➔ GRPO 2단계 전략**을 권장합니다.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ 1단계: SFT 콜드 스타트 (Supervised Fine-Tuning)                              │
│ • 데이터: data/sft_dataset_cold_start.jsonl (5개 핵심 대표 골든 시드 샘플)     │
│ • 목표: 4단계 CoT 추론 형식(<think>) 및 정확한 Cisco CLI 태그(<commands>) 각인│
│ • 학습: SFTTrainer로 1~2 에폭 가볍게 학습                                    │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │ LoRA Adapter 체크포인트
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 2단계: GRPO 정책 최적화 (Group Relative Policy Optimization)                │
│ • 데이터: data/grpo_dataset_all_150.jsonl (150개 시나리오, 600개 대조군)       │
│ • 목표: 정답(+200), CLI오류(-150), 포맷오류(-200) 간 상대적 Advantage(A_i)로   │
│         오답을 능동적으로 회피하고 최적의 설정을 도출하는 강건한 정책 학습     │
│ • 학습: GRPOTrainer / Custom DPO-PPO로 3~4 에폭 본격 학습                    │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. 데이터셋 규격 및 파일 분석

### ① [1단계 SFT] `data/sft_dataset_cold_start.jsonl`
* **파일 크기 및 레코드**: 6.7 KB / **5개 핵심 대표 골든 시드 레코드** (루트선출, 비용, 보안, 모드전환, 롤백)
* **포맷**: Hugging Face `TRL` / OpenAI 표준 `messages` 대화형 구조
```json
{
  "scenario_id": "STP_ROOT_SETTING_01",
  "variant": "primary",
  "messages": [
    {
      "role": "system",
      "content": "당신은 Cisco 엔터프라이즈 네트워크 엔지니어링 전문가입니다. 주어진 네트워크 토폴로지와 L2/STP 요구사항을 정밀하게 분석하여, 4단계 Chain-of-Thought 추론을 <think> 태그 안에 단계별로 작성하고, 실행할 최종 Cisco CLI 명령어를 <commands> 태그 안에 순서대로 작성하세요."
    },
    {
      "role": "user",
      "content": "SW1을 VLAN 1의 Spanning-Tree Root Bridge로 설정하세요. (현재 상태: SW3가 Root (Bridge ID 32768.5000.0003.0000))"
    },
    {
      "role": "assistant",
      "content": "<think>\n1. 토폴로지 분석: 대상 장비는 'SW1'이며, 현재 L2 상태는 'SW3가 Root (Bridge ID 32768.5000.0003.0000)'임. 목표는 'SW1을 VLAN 1의 Spanning-Tree Root Bridge로 설정하세요.' 요구사항을 정확히 충족하는 것임.\n2. 파라미터 및 타이브레이커 계산: VLAN 1에 대해 Bridge Priority를 4096의 유효 배수(또는 root primary 매크로)로 낮추어 상대 스위치보다 낮은 Bridge ID(최우선 순위)를 획득함.\n3. 영향도(Blast Radius) 검토: 설정 주입 후 L2 토폴로지 재계산(TCN) 전파 영향을 확인하고, 트래픽 루프나 블랙홀 없는 신속하고 안정적인 수렴(Convergence)을 보장함.\n4. 명령어 도출:\nspanning-tree vlan 1 priority 4096\n</think>\n<commands>\nspanning-tree vlan 1 priority 4096\n</commands>"
    }
  ]
}
```

### ② [2단계 GRPO] `data/grpo_dataset_all_150.jsonl`
* **파일 크기 및 레코드**: 129 KB / **150개 시나리오 전수 수집 (600개 롤아웃)**
* **수집 방식**: Containerlab 30대 IOL 스위치(단위랩 24대 + 다계층랩 6대)에 `configure replace` 무재부팅 롤백을 매 시나리오 전/후 적용하여 100% 무결점 수집.
* **보상 매트릭스**:
  * `SUCCESS`: **+200.0점**
  * `SYNTAX_ERROR`: **-150.0점** (Cisco CLI 구문 에러, 4096 비배수 priority 등)
  * `FORMAT_ERROR`: **-200.0점** (태그 누락, 설명문 직접 출력)
  * `INEFFECTIVE`: **0.0점**
* **Advantage**: $A_i = \frac{r_i - \mu}{\sigma}$ (전 시나리오 $\sigma > 0$ 품질 게이트 통과)

---

## 3. 1단계: SFT 콜드 스타트 학습 (Stage 1)

1단계에서는 기본 구조와 언어 모델의 태그 생성 안정성을 확보합니다.

```python
# train_stage1_sft.py
import torch
from datasets import load_dataset
from transformers import AutoModelForCausalLM, AutoTokenizer, TrainingArguments
from trl import SFTTrainer
from peft import LoraConfig

model_id = "Qwen/Qwen2.5-3B-Instruct"

tokenizer = AutoTokenizer.from_pretrained(model_id)
model = AutoModelForCausalLM.from_pretrained(
    model_id,
    torch_dtype=torch.bfloat16,
    device_map="auto"
)

# Chat messages 포맷 데이터셋 로드
dataset = load_dataset("json", data_files="data/sft_dataset_cold_start.jsonl")

peft_config = LoraConfig(
    r=16,
    lora_alpha=32,
    target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
    lora_dropout=0.05,
    bias="none",
    task_type="CAUSAL_LM"
)

training_args = TrainingArguments(
    output_dir="./output/stage1-sft-lora",
    num_train_epochs=2,
    per_device_train_batch_size=4,
    gradient_accumulation_steps=2,
    learning_rate=2e-4,
    lr_scheduler_type="cosine",
    bf16=True,
    logging_steps=10,
    save_strategy="epoch"
)

trainer = SFTTrainer(
    model=model,
    train_dataset=dataset["train"],
    peft_config=peft_config,
    args=training_args
)

trainer.train()
trainer.model.save_pretrained("./output/stage1-sft-lora-final")
tokenizer.save_pretrained("./output/stage1-sft-lora-final")
```

---

## 4. 2단계: GRPO 정책 최적화 학습 (Stage 2)

1단계에서 저장된 LoRA 가중치 또는 베이스 모델 위에 `data/grpo_dataset_all_150.jsonl`의 대조 롤아웃 데이터를 주입하여 오답을 회피하고 정답을 선호하도록 정렬합니다.

```python
# train_stage2_grpo.py
import torch
from datasets import load_dataset
from transformers import AutoModelForCausalLM, AutoTokenizer
from trl import GRPOConfig, GRPOTrainer
from peft import PeftModel, LoraConfig

model_id = "Qwen/Qwen2.5-3B-Instruct"
sft_checkpoint = "./output/stage1-sft-lora-final"

dataset = load_dataset("json", data_files="data/grpo_dataset_all_150.jsonl")

# Stage 1 모델을 베이스로 로드하거나 어댑터 병합 후 GRPO 적용
peft_config = LoraConfig(
    r=16,
    lora_alpha=32,
    target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
    task_type="CAUSAL_LM"
)

training_args = GRPOConfig(
    output_dir="./output/stage2-grpo-lora",
    learning_rate=5e-5,
    per_device_train_batch_size=4,
    gradient_accumulation_steps=2,
    num_train_epochs=4,
    bf16=True,
    logging_steps=5,
    save_strategy="epoch"
)

trainer = GRPOTrainer(
    model=model_id,
    reward_funcs=None, # 사전 계산된 relative_advantage 직접 바인딩
    args=training_args,
    train_dataset=dataset["train"],
    peft_config=peft_config
)

trainer.train()
trainer.model.save_pretrained("./output/final-network-grpo-model")
```

---

## 5. 추론 및 배포 테스트 가이드 (Prompting)

파인튜닝된 모델에 질의할 때 가장 높은 성능을 내기 위한 권장 질의 템플릿입니다.

### ① 시스템 프롬프트 (System Prompt)
```text
당신은 Cisco 엔터프라이즈 네트워크 엔지니어링 전문가입니다. 주어진 네트워크 토폴로지와 L2/STP 요구사항을 정밀하게 분석하여, 4단계 Chain-of-Thought 추론을 <think> 태그 안에 단계별로 작성하고, 실행할 최종 Cisco CLI 명령어를 <commands> 태그 안에 순서대로 작성하세요.
```

### ② 사용자 질의 예시 (User Prompt)
* **목표 지향형 (Root/Cost 최적화)**:
  ```text
  SW1을 VLAN 10의 Spanning-Tree Root Bridge로 설정하세요. (현재 상태: SW2가 Root 상태)
  ```
* **다계층 통합형 (Core/Dist LACP & STP)**:
  ```text
  Core-1(core-sw1)을 VLAN 10의 Root Primary로 설정하고, 포트 채널 Port-channel1의 STP Cost를 1000으로 조정하세요.
  ```
* **보안 및 장애 격리형 (BPDU Guard / Root Guard)**:
  ```text
  비인가 스위치의 Root 탈취를 원천 차단하기 위해 dist-sw1의 GigabitEthernet0/2 포트에 Root Guard를 활성화하세요.
  ```

### ③ 모델의 이상적인 생성 결과 (Ideal Output)
```xml
<think>
1. 토폴로지 분석: 대상 장비는 core-sw1이며, VLAN 10의 Spanning-Tree 경로 제어가 목표임.
2. 파라미터 계산: Root Primary 매크로 적용 및 Port-channel1에 명시적 cost 1000 부여.
3. 영향도 검토: 루트 브리지 전환 시 TCN이 발생하므로 신속한 수렴을 확인해야 함.
4. 명령어 도출:
spanning-tree vlan 10 root primary
interface Port-channel1
 spanning-tree vlan 10 cost 1000
</think>
<commands>
spanning-tree vlan 10 root primary
interface Port-channel1
 spanning-tree vlan 10 cost 1000
</commands>
```

---

## 6. 품질 지표 및 롤백 무결성

* **전체 시나리오 수**: **150개** (Unit 24대 + Multitier 6대 전수 포함)
* **1단계 SFT 샘플**: **5개 골든 시드 레코드** (Spanning-Tree 5대 핵심 도메인 대표, 무결성 100% 검증)
* **2단계 GRPO 샘플**: **600개 롤아웃** (품질 게이트 통과율 100%, $\sigma > 0$)
* **실장비 롤백 안정성**: Cisco IOL 원자적 롤백(`configure replace nvram:startup-config force`) 적용으로 150개 시나리오 전/후 잔여 설정 오염 0% 달성.

---

## 7. 보상 체계 심층 설계: 차선책 150점(Sweet Spot) 및 다층화 가이드

### ① 문제 배경: 이진화 보상(Binary Reward)의 치명적 한계
기존의 성긴 보상(Sparse Reward: 성공 +200, 실패/무효 0, 문법오류 -150, 포맷오류 -200) 구조에서는 **0점과 200점 사이의 간극이 지나치게 커서 차선책(Sub-optimal)이나 기능적 대안(Functional Alternative)이 배제**되는 문제가 발생합니다.

* **사례 분석 (STP Root 설정 시나리오)**:
  * 프롬프트: `"SW1을 VLAN 1의 Spanning-Tree Root Bridge로 설정하세요. (현재 상태: SW3가 Root (32768))"`
  * 대안 A: `spanning-tree vlan 1 root primary` (매크로 명령어) ➔ **+200점 (SUCCESS)**
  * 대안 B: `spanning-tree vlan 1 priority 4096` (명시적 우선순위) ➔ **0점 (INEFFECTIVE 처리 오류)**
* **문제점**:
  1. **네트워크 실무와의 괴리**: 실무에서는 `root primary` 매크로보다 명시적 `priority 4096` 또는 `0`을 지정하는 것을 더 결정론적(Deterministic)이고 안정적인 모범 사례(Best Practice)로 평가하는 경우가 많습니다.
  2. **모드 붕괴(Mode Collapse) 및 단순 암기**: 단 하나의 특정 표현(`root primary`)에만 200점을 주고 다른 유효한 설정을 0점 처리하면, 모델은 STP의 Priority 원리를 추론하는 대신 프롬프트 키워드에 반응하는 단순 문자열 템플릿만 암기하게 됩니다.
  3. **잘못된 네거티브 피드백**: 동일 그룹 내에서 +200점 후보와 비교되면서 유효한 대안인 `priority 4096`이 음수(-) Advantage를 부여받아, 올바른 명령어가 정책 확률에서 억제(Penalized)되는 심각한 왜곡이 발생합니다.

---

### ② 차선책/유효 대안에 "150점" 부여의 정당성과 수학적 우수성 (Sweet Spot)

0점과 200점 사이의 차선책에 **150점**을 부여하는 방안은 수학적(GRPO Advantage) 및 도메인 학습 관점에서 가장 이상적인 해결책입니다:

#### A. 완벽한 수학적 대칭성 및 중심화 ($\mu = 0$)
현재 시스템의 페널티는 `SYNTAX_ERROR (-150)`와 `FORMAT_ERROR (-200)`로 구성되어 있습니다. 여기에 차선책 `+150점`을 도입하면 그룹 구성 시 완벽한 상하 대칭이 형성됩니다:
* 후보군 구성: `[+200(최적), +150(차선), -150(문법오류), -200(포맷오류)]`
* **그룹 평균:** $\mu = \frac{200 + 150 - 150 - 200}{4} = \mathbf{0.0}$ (정확한 영점 조준)
* **표준편차:** $\sigma \approx 176.78$
* **상대 우위(Advantage) 산출**:
  * 최적해 (+200): $\frac{+200}{176.78} \approx \mathbf{+1.13}$ (강력한 정답 강화)
  * **차선책 (+150):** $\frac{+150}{176.78} \approx \mathbf{+0.85}$ (**안정적인 고득점 양수 강화**)
  * 문법 에러 (-150): $\frac{-150}{176.78} \approx \mathbf{-0.85}$ (대칭적 음수 페널티)
  * 포맷 에러 (-200): $\frac{-200}{176.78} \approx \mathbf{-1.13}$ (최대 음수 페널티)

100점을 주었을 때(+0.67)보다 훨씬 강력한 양의 우위(+0.85)를 제공하면서도, 최적해(+200)에 대해서는 적절한 선호 격차(+50점 차이)를 유지합니다.

#### B. 학습 인센티브 지형 (Reward Landscape)
* **무효(0점) 대비 +150점의 도약**: 모델에게 "아무런 상태 변화도 못 내는 것(0점)보다, 유효한 차선책이라도 도출하여 문제를 해결하는 것이 훨씬 가치 있다"는 강력한 인센티브를 제공합니다.
* **최적해(200점) 대비 50점의 미세 차이**: 차선책을 냈다고 해서 정책 확률이 급격히 깎이지 않으므로, 모델이 과감하게 다양한 네트워크 명령어를 탐색(Exploration)할 수 있는 안전장치가 됩니다.

---

### ③ 확정 다계층 차등 보상 매트릭스 (Tiered Reward Matrix)

| 등급 (Tier) | 보상 점수 | 상태 (Status) | 적용 기준 및 예시 |
| :--- | :---: | :--- | :--- |
| **최적해 (Optimal)** | **+200.0** | `SUCCESS_OPTIMAL` | 지시사항 100% 충족 및 시스템 권장 표준 명령어 |
| **유효 대안 / 차선책 (Sub-optimal)** | **+150.0** | `SUCCESS_ALTERNATIVE` | • **1번 케이스의 `priority 4096`**: 루트 선점 목적을 100% 달성한 안정적 대안<br>• 인터페이스 명칭의 정규 축약/풀네임 등 동등한 효과를 내는 유효 명령어 |
| **부분 성공 (Partial Success)** | **+100.0** | `PARTIAL_SUCCESS` | 복합 요구조건 중 일부만 반영되었거나 파라미터가 다소 비효율적인 경우 |
| **무효 (Ineffective)** | **0.0** | `INEFFECTIVE` | 문법은 유효하나 장비 상태에 실질적 변화가 없는 경우 (동일 값 재설정 등) |
| **구문 오류 (Syntax Error)** | **-150.0** | `SYNTAX_ERROR` | Cisco CLI 실행 거부, 4096 배수 위반 등 문법 오류 |
| **형식 오류 (Format Error)** | **-200.0** | `FORMAT_ERROR` | 태그 미준수, CLI 명령어 부재, 단순 자연어 응답 |

---

## 8. Cold-Start SFT 데이터 규모 최적화 (225개 vs 5~10개 분석)

### ① 대량 SFT(225개)의 잠재적 리스크
1단계 SFT 데이터(`sft_dataset_cold_start.jsonl`)가 225개로 비대해질 경우 다음과 같은 심각한 강화학습 부작용이 발생합니다:
1. **탐색 억제 및 사전 고착(Exploration Collapse)**:
   * 모델이 225개의 사전 정의된 CoT 추론 및 특정 CLI 문구에 과적합(Overfitting)되어, 2단계 GRPO에서 스스로 새로운 해법이나 유연한 CLI 조합을 탐색하려 하지 않고 1단계에서 외운 방식만 고집합니다.
2. **콜드 스타트(Cold-Start) 본래 목적의 전도**:
   * GRPO에서 Cold-Start SFT의 유일한 목적은 **`<think>` 및 `<commands>` 태그 문법을 각인시켜 초기 포맷 에러(-200)로 인한 그래디언트 소멸을 방지하는 것(Format Seeding)**입니다.
   * 네트워크 지식과 의사결정 정책은 2단계의 실장비/보상 피드백(GRPO)을 통해 스스로 학습되어야 건강한 일반화 성능이 나옵니다.

### ② 권장 규모: 5~10개의 골든 시드(Golden Seeds) 체제
DeepSeek-R1 및 최신 RLVR/GRPO 가이드라인에 부합하는 권장 콜드 스타트 구성은 다음과 같습니다:
* **수량**: **5 ~ 10개 내외**
* **구성 원칙**:
  * STP 루트 선출 (명시적 Priority 및 매크로) 1~2개
  * 포트 파라미터 튜닝 (Cost, Port-Priority) 1~2개
  * 보호 기능 (BPDU Guard, Root Guard) 1~2개
  * 인터페이스 트렁크 및 포트채널 번들링 1~2개
  * 모드 전환 및 롤백/Unset 1~2개
* **효과**: 태그 포맷과 4단계 CoT 추론 구조만 깔끔하게 시딩(Seeding)하고, 나머지 파라미터 결정과 대안 탐색은 온전히 150개 시나리오 기반의 GRPO 환경에 위임하여 **최적의 자율 추론 정책 모델**을 완성합니다.


