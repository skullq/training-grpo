# Cisco L2/STP Network Qwen2.5-3B LoRA Pipeline

Cisco 엔터프라이즈 L2/STP 네트워크 도메인에 특화된 **Qwen2.5-3B-Instruct 모델의 LoRA 파인튜닝 파이프라인**입니다.
Linux 가상 랩 환경(Cisco IOL via Containerlab)에서 실장비 검증을 완료하고, **개인 맥북 M4 (Apple Silicon 24~32GB)**에서 외부 랩 연결 없이 즉시 오프라인 학습할 수 있는 정제된 데이터셋과 학습 스크립트를 제공합니다.

---

## 📚 핵심 문서

- **[📘 마스터 기술 문서 (technical-note.md)](technical-note.md)**: 전체 아키텍처, 1초 원자적 롤백 노이즈 차단 원리, 데이터셋 포맷, M4 튜닝 가이드 요약
- **[💻 맥북 M4 LoRA 파인튜닝 실무 가이드 (docs/M4_LORA_TRAINING_GUIDE.md)](docs/M4_LORA_TRAINING_GUIDE.md)**: MLX, Hugging Face TRL SFT, DPO 환경 구축 및 상세 실행 방법
- **[📊 데이터셋 품질 개선 및 실장비 검증 보고서 (docs/DATASET_IMPROVEMENT_REPORT.md)](docs/DATASET_IMPROVEMENT_REPORT.md)**: 150/150 실장비 검증 상세 및 보상 분포 분석

---

## 📁 데이터셋 구조 (`data/`)

모든 데이터는 실장비 검증(100% 통과)을 거쳤으며, 엔지니어링 4단계 CoT 추론(`<think>`, `<commands>`)이 내장되어 있습니다.

| 경로 | 용도 | 건수 | 권장 학습 도구 |
| :--- | :--- | :---: | :--- |
| **`data/mlx/train.jsonl`** | **M4 초고속 LoRA SFT** | **130** | **`./train_m4_mlx.sh` (3~4분 소요, 추천 ⭐)** |
| `data/mlx/valid.jsonl` | M4 MLX 검증용 | 20 | `evaluate_m4.py` |
| `data/sft/train.jsonl` | HF TRL SFTTrainer 포맷 | 130 | `train_m4_sft.py` (PyTorch MPS) |
| `data/sft/valid.jsonl` | HF TRL 검증용 | 20 | `evaluate_m4.py` |
| `data/dpo/train.jsonl` | 랩 없는 선호도 대조 정렬 | 130 | `train_m4_dpo.py` (Chosen vs Rejected) |
| `data/dpo/valid.jsonl` | DPO 검증용 | 20 | `evaluate_m4.py` |
| `data/grpo/grpo_dataset_150_repaired.jsonl` | 오프라인 GRPO 완전 교정본 | 150 (600 rollouts) | GRPOTrainer / `view_dataset.py` |

---

## ⚡ 맥북 M4에서 빠른 시작 (Quick Start)

맥북 터미널에서 본 저장소를 클론한 후 바로 실행할 수 있습니다:

```bash
# 1. 초고속 Apple MLX LoRA 학습 (가장 추천, ~3분 소요)
pip install mlx-lm
./train_m4_mlx.sh

# 2. 독립 20개 테스트셋 정답률 자동 채점
python evaluate_m4.py --engine mlx --adapter ./output/m4-mlx-qwen-lora
```

---

## 🛠️ 실장비 랩 검증 및 검사 도구

신규 20문제의 초기 상태, 요구 설정, 실제 동작 및 원복 판정 기준은
[랩 테스트 검증 항목](docs/LAB_TRANSFER_GUIDE.md)에 있습니다.
다른 컴퓨터에서 이어갈 현재 상태, 배선, 20문제와 결과 양식은
[단일 인계 문서](lab-pc.md)에 모았습니다.
자료는 미승인·미검증 초안이며 모델 응답은 아직 생성하지 않았습니다.

```bash
# 데이터셋 무결성 전수 검사 (태그, 분산, 포맷)
uv run python scripts/verify_m4_datasets.py

# GRPO 데이터셋 CLI 프리티 뷰어
uv run python view_dataset.py --limit 3
```
