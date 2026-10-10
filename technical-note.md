# 📘 네트워크 3B 모델 LoRA 파인튜닝 & 실장비 검증 테크니컬 노트

본 문서는 Cisco 엔터프라이즈 L2/STP 도메인에 특화된 **Qwen2.5-3B-Instruct 모델의 LoRA 파인튜닝**을 위해, **Linux 랩 서버의 실장비 라이브 검증**과 **개인 맥북 M4의 오프라인 학습 파이프라인**을 연계한 엔지니어링 기술 문서입니다.

---

## 1. 2-Tier 분리형 파이프라인 아키텍처

실제 가상 스위치 환경(Linux)과 개인 학습 환경(MacBook M4)을 완전히 분리하여 운영합니다.

```
┌────────────────────────────────────────────────────────────────────────┐
│ [Tier 1] Linux 랩 서버 (Containerlab + Cisco IOL L2-17.17.01)          │
├────────────────────────────────────────────────────────────────────────┤
│ • 150개 멀티티어 L2/STP 시나리오 원본 마스터 관리                      │
│ • 1초 원자적 롤백 (configure replace nvram:startup-config force) 격리   │
│ • Cisco IOL 실장비 전수 주입 검증 (150/150 시나리오 100% 성공)          │
│ • 실장비 검증 완료 4대 데이터셋 자동 생성 (MLX, SFT, DPO, GRPO)        │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │ Git Clone / Pull (데이터셋 & 스크립트만 복제)
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│ [Tier 2] 맥북 M4 (Apple Silicon 24~32GB Unified Memory)                │
├────────────────────────────────────────────────────────────────────────┤
│ • 랩 연결 0% (완전 오프라인 환경에서 데이터셋 기반 LoRA 학습)          │
│ • [추천 1순위] Apple MLX LoRA SFT: ./train_m4_mlx.sh (약 3분 완료)     │
│ • [표준 HF] PyTorch MPS SFT: python train_m4_sft.py                    │
│ • [오프라인 DPO] 선호도 대조 정렬: python train_m4_dpo.py (오답 회피)   │
│ • [자동 채점] 20개 독립 테스트셋 평가: python evaluate_m4.py           │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 2. 실장비 랩 검증 및 노이즈 원천 차단 (Zero Contamination)

이전 시나리오의 설정 잔여물(Priority, Cost, PortFast 등)로 인한 간섭을 제거하기 위해 **무재부팅 1초 원자적 롤백 메커니즘**을 확립하였습니다.

### ① 무재부팅 1초 원자적 격리 절차
1. **골든 베이스라인 고정**: 부팅 시 `configs/initial_config.cfg` 주입 후 `write memory`로 `startup-config`를 영구 저장.
2. **사전 원자적 롤백**: 매 시나리오 실행 전 `configure replace nvram:startup-config force`를 수행하여 스위치를 완전 초기 상태로 복구 (소요시간 1초 미만).
3. **실장비 명령어 주입**: Cisco IOL 실장비에 CLI 주입 및 `% Invalid input detected` 등 오류 실측.
4. **사후 원자적 롤백**: 시나리오 검증 즉시 다시 롤백을 수행하여 **시나리오 간 설정 오염 0.0%** 달성.

### ② 실장비 검증 피드백 및 IOL 문법 동기화
* **물리 인터페이스 정규화**: Cisco IOL 스위치는 `GigabitEthernet` 인터페이스가 없으므로 `Ethernet0/1 ~ Ethernet0/3`으로 전수 매핑.
* **PortFast 표준화**: NX-OS 전용 `portfast edge` 대신 Cisco IOL 지원 표준인 `spanning-tree portfast` 및 `spanning-tree portfast trunk`로 교정.
* **최종 검증 실측치**: **150개 시나리오 전수 라이브 주입 성공 (통과율 100.0%)** ([검증 로그](docs/live_lab_validation_report_v2.json))

---

## 3. 정제된 데이터셋 구성 및 선택 가이드

과거 레거시 파일 및 중간 임시 파일은 모두 삭제되었으며, 현재 `data/` 디렉토리에는 검증된 최신 데이터만 유지됩니다.

```
data/
├── mlx/                      # ⭐ [맥북 M4 1순위 권장] Apple MLX 네이티브 포맷
│   ├── train.jsonl           # 130개 학습셋
│   └── valid.jsonl           # 20개 검증셋
├── sft/                      # Hugging Face TRL SFTTrainer 표준 포맷
│   ├── train.jsonl           # 130개 학습셋
│   └── valid.jsonl           # 20개 검증셋
├── dpo/                      # 랩 없는 오프라인 DPO 선호도 정렬 포맷
│   ├── train.jsonl           # 130개 (chosen vs rejected 페어)
│   └── valid.jsonl           # 20개 검증셋
├── grpo/                     # 오프라인 GRPO 완전 교정본
│   └── grpo_dataset_150_repaired.jsonl  # 150개 시나리오 (600 롤아웃, σ > 0 보장)
└── grpo_scenario_multitier_150.json     # 150개 원본 시나리오 마스터
```

### 🎯 맥북 M4에서 어떤 파일을 가져다 학습해야 하는가?
* **LoRA 파인튜닝 (기본)**: 👉 **`data/mlx/train.jsonl`** (MLX 프레임워크) 또는 **`data/sft/train.jsonl`** (PyTorch TRL)
* **오답 회피 선호도 정렬**: 👉 **`data/dpo/train.jsonl`**
* **평가/채점**: 👉 **`data/mlx/valid.jsonl`** 또는 **`data/sft/valid.jsonl`**

### 4단계 CoT 추론 구조
모든 데이터의 모델 응답은 환각을 방지하고 엔지니어링 논리를 주입하기 위해 아래 태그 규격으로 통일되어 있습니다:
```xml
<think>
1. 토폴로지 분석: 대상 장비는 'SW1'이며 현재 상태는 'SW3가 Root'임.
2. 파라미터 및 타이브레이커 계산: VLAN 1의 Bridge Priority를 4096으로 조정함.
3. 영향도(Blast Radius) 검토: TCN 발생 후 1초 내 Rapid 수렴 보장.
4. 명령어 도출:
spanning-tree vlan 1 priority 4096
</think>
<commands>
spanning-tree vlan 1 priority 4096
</commands>
```

---

## 4. 맥북 M4 LoRA 파인튜닝 실행 가이드

맥북 M4(24~32GB 통합 메모리)에서 저장소를 클론한 후 즉시 실행할 수 있습니다.

### ① Apple MLX 초고속 LoRA SFT (가장 추천 ⭐)
Apple Silicon Unified Memory 최적화를 통해 약 **3~4분 만에 3B 모델 LoRA 파인튜닝을 완료**합니다.
```bash
pip install mlx-lm
./train_m4_mlx.sh
```
* **데이터셋**: `data/mlx/train.jsonl`
* **출력 디렉토리**: `./output/m4-mlx-qwen-lora`

### ② Hugging Face PyTorch MPS SFT
표준 Hugging Face 생태계를 사용할 경우:
```bash
pip install transformers datasets trl peft torch accelerate
python train_m4_sft.py
```
* **데이터셋**: `data/sft/train.jsonl`
* **디바이스**: Apple Silicon MPS (`torch.backends.mps`)

### ③ 오프라인 DPO 선호도 정렬
SFT 모델을 기반으로, 랩 연결 없이 실제 엔지니어링 오답(`rejected`)을 스스로 회피하도록 가중치를 정렬합니다:
```bash
python train_m4_dpo.py
```
* **데이터셋**: `data/dpo/train.jsonl` (chosen vs rejected)

### ④ 모델 추론 및 자동 채점
학습 완료 후 독립된 20개 Validation 시나리오에 대해 정확도를 자동 채점합니다:
```bash
# MLX LoRA 모델 평가
python evaluate_m4.py --engine mlx --adapter ./output/m4-mlx-qwen-lora

# Hugging Face LoRA 모델 평가
python evaluate_m4.py --engine hf --adapter ./output/m4-sft-lora-final
```

---

## 5. 핵심 파일 및 도구 맵

| 구분 | 파일 경로 | 설명 | 주요 환경 |
| :--- | :--- | :--- | :---: |
| **M4 학습** | `train_m4_mlx.sh` | Apple MLX 기반 초고속 LoRA 학습 스크립트 | 맥북 M4 |
| **M4 학습** | `train_m4_sft.py` | PyTorch MPS + TRL SFTTrainer 스크립트 | 맥북 M4 |
| **M4 정렬** | `train_m4_dpo.py` | PyTorch MPS + TRL DPOTrainer 선호도 정렬 스크립트 | 맥북 M4 |
| **M4 평가** | `evaluate_m4.py` | 20개 독립 테스트셋 LoRA 추론 및 자동 채점기 | 맥북 M4 |
| **오프라인 채점** | `src/offline_reward.py` | 외부 랩 연결 없는 독립 Cisco 구문/보상 채점 엔진 | 공용 |
| **데이터 검증** | `scripts/verify_m4_datasets.py` | 데이터셋 태그 및 무결성 전수 검증 도구 | 공용 |
| **데이터 뷰어** | `view_dataset.py` | 터미널 테이블 기반 GRPO 데이터셋 프리티 뷰어 | 공용 |
| **실장비 검증** | `scripts/run_live_lab_validation_v2.py` | 1초 원자적 롤백 기반 150개 실장비 주입 검증기 | Linux 랩 |
| **데이터셋 빌드** | `scripts/build_m4_datasets.py` | 실장비 검증 반영 4종 M4 데이터셋 빌더 | Linux 랩 |
