#!/bin/bash
# ==============================================================================
# Apple Silicon Mac (M4 / M4 Pro / M4 Max) Native LoRA 파인튜닝 스크립트
# Framework: Apple MLX (mlx-lm) — Unified Memory 최적화, 최고 속도
# Target Model: Qwen/Qwen2.5-3B-Instruct (또는 4bit 양자화 모델)
# ==============================================================================

set -e

echo "=========================================================="
echo " 🍏 Apple Silicon M4 MLX LoRA Fine-Tuning 시작"
echo "=========================================================="

# 1. 의존성 확인 및 안내
if ! command -v mlx_lm.lora &> /dev/null; then
    echo "⚠️  mlx-lm 패키지가 설치되지 않았습니다."
    echo "설치 명령어: pip install mlx-lm"
    echo ""
fi

MODEL_ID="Qwen/Qwen2.5-3B-Instruct"
DATA_DIR="data/mlx"
OUTPUT_DIR="./output/m4-mlx-qwen-lora"
BATCH_SIZE=4
NUM_ITERS=400
LEARNING_RATE=1e-4
LORA_LAYERS=16

echo "설정 파라미터:"
echo "  - 베이스 모델: ${MODEL_ID}"
echo "  - 학습 데이터: ${DATA_DIR} (train.jsonl / valid.jsonl)"
echo "  - 출력 디렉토리: ${OUTPUT_DIR}"
echo "  - 배치 크기: ${BATCH_SIZE}"
echo "  - 학습 스텝: ${NUM_ITERS} iters"
echo "  - LoRA 레이어: ${LORA_LAYERS}"
echo "=========================================================="

python -m mlx_lm.lora \
    --model "${MODEL_ID}" \
    --train \
    --data "${DATA_DIR}" \
    --batch-size ${BATCH_SIZE} \
    --iters ${NUM_ITERS} \
    --learning-rate ${LEARNING_RATE} \
    --lora-layers ${LORA_LAYERS} \
    --adapter-path "${OUTPUT_DIR}" \
    --save-every 100 \
    --test

echo ""
echo "=========================================================="
echo " 🎉 MLX LoRA 파인튜닝 완료! 어댑터 위치: ${OUTPUT_DIR}"
echo "=========================================================="
