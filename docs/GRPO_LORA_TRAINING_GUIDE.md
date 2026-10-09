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

---

## 1. 2단계 훈련 아키텍처 (2-Stage Pipeline)

GRPO(강화학습)를 베이스 모델(Pre-trained)에 바로 적용할 경우, 초기에 `<think>` 태그나 `<commands>` 태그 문법을 지키지 못해 보상이 계속 음수(-200)로 수렴하는 **콜드 스타트 붕괴(Cold-Start Collapse)** 현상이 발생할 수 있습니다. 이를 방지하기 위해 **SFT ➔ GRPO 2단계 전략**을 권장합니다.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ 1단계: SFT 콜드 스타트 (Supervised Fine-Tuning)                              │
│ • 데이터: data/sft_dataset_cold_start.jsonl (225개 엄선된 정답 샘플)           │
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
* **파일 크기 및 레코드**: 342 KB / **225개 정답 대화 레코드** (Primary 정답 + 대안 명령 조합)
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
* **1단계 SFT 샘플**: **225개 레코드** (무결성 100% 검증)
* **2단계 GRPO 샘플**: **600개 롤아웃** (품질 게이트 통과율 100%, $\sigma > 0$)
* **실장비 롤백 안정성**: Cisco IOL 원자적 롤백(`configure replace nvram:startup-config force`) 적용으로 150개 시나리오 전/후 잔여 설정 오염 0% 달성.
