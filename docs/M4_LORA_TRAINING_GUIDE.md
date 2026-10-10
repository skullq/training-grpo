# 🍏 맥북 M4 (Apple Silicon) 전용 네트워크 LoRA 파인튜닝 완벽 가이드

이 문서는 **Containerlab/가상 스위치 랩이 설치되지 않은 개인 맥북(Apple Silicon M4 / M4 Pro / M4 Max, 메모리 24~32GB)**에서, 이 Git 리포지토리의 정제된 데이터셋만 가져다가 즉시 LoRA 파인튜닝을 수행하기 위한 공식 가이드입니다.

---

## 📌 목차
1. [핵심 아키텍처 및 훈련 전략](#1-핵심-아키텍처-및-훈련-전략)
2. [데이터셋 규격 및 디렉토리 구조](#2-데이터셋-규격-및-디렉토리-구조)
3. [맥북 M4 환경 준비 (3분 셋업)](#3-맥북-m4-환경-준비-3분-셋업)
4. [훈련 트랙 1: Apple MLX LoRA (초고속, 추천 ⭐)](#4-훈련-트랙-1-apple-mlx-lora-초고속-추천-)
5. [훈련 트랙 2: PyTorch MPS + Hugging Face TRL SFT](#5-훈련-트랙-2-pytorch-mps--hugging-face-trl-sft)
6. [훈련 트랙 3: 오프라인 DPO 선호도 정렬 (랩 없는 정렬 학습)](#6-훈련-트랙-3-오프라인-dpo-선호도-정렬-랩-없는-정렬-학습)
7. [M4 성능 평가 및 자동 채점](#7-m4-성능-평가-및-자동-채점)
8. [M4 하드웨어 메모리별 권장 설정 표](#8-m4-하드웨어-메모리별-권장-설정-표)

---

## 1. 핵심 아키텍처 및 훈련 전략

> [!NOTE]
> **왜 맥북 M4에서는 랩(Live Lab) 연결이 필요 없는가?**
> - 모든 L2/STP 시나리오(150개)의 정답 명령어, 문법 규칙, 4단계 CoT 추론, 오답 패턴은 이미 랩 서버에서 전수 검증되어 **고품질 오프라인 데이터셋**으로 구축되었습니다.
> - 맥북 M4에서는 가상 랩 환경 없이 순수 데이터셋만으로 **지도 미세조정(SFT)** 및 **직접 선호도 최적화(DPO)**를 수행하여 3B 모델을 완벽한 네트워크 엔지니어로 튜닝할 수 있습니다.

```
┌────────────────────────────────────────────────────────────────────────┐
│                        맥북 M4 로컬 훈련 파이프라인                     │
├────────────────────────────────────────────────────────────────────────┤
│  [Step 1. SFT 단계] data/sft/train.jsonl (130개)                      │
│   • 4단계 CoT (<think>) 및 Cisco CLI (<commands>) 형식 완전 각인       │
│   • Apple MLX (train_m4_mlx.sh) 또는 TRL (train_m4_sft.py) 로 학습      │
│                                  │                                     │
│                                  ▼ LoRA 어댑터 체크포인트               │
│  [Step 2. DPO 정렬 단계] data/dpo/train.jsonl (130개)                  │
│   • 정답(chosen: 골든 CoT + 정상 CLI) vs 오답(rejected: 문법/포맷 에러)│
│   • 랩 없이도 문법 오류 및 비효과적 설정을 스스로 회피하도록 정렬      │
│                                  │                                     │
│                                  ▼ 최종 파인튜닝 모델                   │
│  [Step 3. 검증 단계] data/sft/valid.jsonl (20개)                      │
│   • python evaluate_m4.py 로 정답률(SUCCESS) 및 문법 무결성 자동 채점  │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 2. 데이터셋 규격 및 디렉토리 구조

이 리포지토리에는 M4 학습을 위한 4가지 표준 데이터셋이 완비되어 있습니다.

```
training-grpo/
├── data/
│   ├── sft/                       # 1단계 SFT용 (130 Train / 20 Valid)
│   │   ├── train.jsonl
│   │   └── valid.jsonl
│   ├── mlx/                       # Apple MLX Native 포맷
│   │   ├── train.jsonl
│   │   └── valid.jsonl
│   ├── dpo/                       # 2단계 DPO 선호도 정렬용 (130 Train / 20 Valid)
│   │   ├── train.jsonl
│   │   └── valid.jsonl
│   └── grpo/
│       └── grpo_dataset_150_repaired.jsonl  # 결함 완전 해소된 오프라인 GRPO
```

### 데이터 레코드 예시 (SFT)
```json
{
  "scenario_id": "STP_ROOT_SETTING_01",
  "messages": [
    {"role": "system", "content": "당신은 Cisco 엔터프라이즈 네트워크 엔지니어링 전문가입니다..."},
    {"role": "user", "content": "SW1을 VLAN 1의 Spanning-Tree Root Bridge로 설정하세요. (현재 상태: SW3가 Root)"},
    {"role": "assistant", "content": "<think>\n1. 토폴로지 분석: 대상 장비는 'SW1'...\n2. 파라미터 계산: Priority 4096 적용...\n3. 영향도 검토: TCN 발생 후 안정적 수렴...\n4. 명령어 도출:\nspanning-tree vlan 1 priority 4096\n</think>\n<commands>\nspanning-tree vlan 1 priority 4096\n</commands>"}
  ]
}
```

---

## 3. 맥북 M4 환경 준비 (3분 셋업)

맥북 터미널을 열고 리포지토리를 가져온 뒤 가상환경을 구성합니다.

```bash
# 1. 저장소 클론 및 이동
git clone <your-repo-url> training-grpo
cd training-grpo

# 2. Python 가상환경 생성 (Python 3.10 이상)
python3 -m venv .venv
source .venv/bin/activate

# 3. 필수 의존성 패키지 설치
# (Apple MLX 및 Hugging Face 생태계 동시 지원)
pip install --upgrade pip
pip install mlx-lm transformers datasets trl peft torch accelerate rich
```

---

## 4. 훈련 트랙 1: Apple MLX LoRA (초고속, 추천 ⭐)

Apple Silicon의 통합 메모리(Unified Memory)를 100% 활용하는 **MLX** 프레임워크입니다.
M4 24GB~32GB 메모리 환경에서 가장 발열이 적고 약 3~5분 내에 학습이 완료됩니다.

### 실행 방법
```bash
./train_m4_mlx.sh
```

### 상세 내부 옵션 (`train_m4_mlx.sh`)
```bash
python -m mlx_lm.lora \
    --model Qwen/Qwen2.5-3B-Instruct \
    --train \
    --data data/mlx \
    --batch-size 4 \
    --iters 400 \
    --learning-rate 1e-4 \
    --lora-layers 16 \
    --adapter-path ./output/m4-mlx-qwen-lora \
    --save-every 100 \
    --test
```
* 학습 완료 후 어댑터 가중치는 `./output/m4-mlx-qwen-lora`에 자동 저장됩니다.

---

## 5. 훈련 트랙 2: PyTorch MPS + Hugging Face TRL SFT

표준 Hugging Face 생태계(`transformers` + `trl` + `peft`)를 선호할 때 사용하는 파이프라인입니다. PyTorch의 **MPS(Metal Performance Shaders)** 가속기를 사용합니다.

### 실행 방법
```bash
python train_m4_sft.py
```

* **에폭(Epochs)**: 3 에폭
* **배치 사이즈**: 2 (Gradient Accumulation 4 = 유효 배치 8)
* **결과 저장**: `./output/m4-sft-lora-final`

---

## 6. 훈련 트랙 3: 오프라인 DPO 선호도 정렬 (랩 없는 정렬 학습)

RLHF/GRPO 대신 오프라인에서 정답(chosen)과 오답(rejected)을 대조 학습하여, 모델이 잘못된 우선순위(예: 5000), 구문 오류, 포맷 누락을 스스로 걸러내도록 가중치를 정렬합니다.

### 실행 방법
```bash
# 1단계 SFT 모델 기반 DPO 정렬
python train_m4_dpo.py
```

* **학습 데이터**: `data/dpo/train.jsonl` (130개 대조군) & `valid.jsonl` (20개)
* **결과 저장**: `./output/m4-dpo-lora-final`

---

## 7. M4 성능 평가 및 자동 채점

학습이 끝난 어댑터 모델의 실력을 20개 독립 테스트 시나리오(Held-out Validation)에 대해 즉시 검증합니다.

```bash
# 1. Hugging Face SFT 모델 평가
python evaluate_m4.py --engine hf --adapter ./output/m4-sft-lora-final

# 2. Hugging Face DPO 정렬 모델 평가
python evaluate_m4.py --engine hf --adapter ./output/m4-dpo-lora-final

# 3. Apple MLX 모델 평가
python evaluate_m4.py --engine mlx --adapter ./output/m4-mlx-qwen-lora
```

### 출력 예시
```text
Evaluating 20 validation scenarios...
[01/20] STP_ROOT_SETTING_02              | 상태: SUCCESS      | 보상: +200.0
[02/20] STP_ROOT_SECONDARY_11           | 상태: SUCCESS      | 보상: +200.0
[03/20] STP_PORT_COST_22                | 상태: SUCCESS      | 보상: +200.0
...
==================================================
  평가 결과: 정답률(SUCCESS) = 20/20 (100.0%)
==================================================
```

---

## 8. M4 하드웨어 메모리별 권장 설정 표

| 맥북 사양 | 통합 메모리 | 권장 프레임워크 | 베이스 모델 | Batch Size | 훈련 시간(예상) |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **M4 기본형** | 16GB | MLX (4bit 양자화 권장) | `Qwen/Qwen2.5-3B-Instruct` | 2 | ~4분 |
| **M4 / M4 Pro** | **24GB ~ 32GB (현재)** | **MLX 또는 PyTorch MPS** | **`Qwen/Qwen2.5-3B-Instruct` (bf16)** | **4** | **~3분 (MLX) / ~7분 (HF)** |
| **M4 Max** | 48GB ~ 128GB | PyTorch MPS / MLX | `Qwen/Qwen2.5-7B-Instruct` 확장 가능 | 8 | ~2분 |
