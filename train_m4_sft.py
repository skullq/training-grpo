"""
Apple Silicon Mac (M4 / M4 Pro / M4 Max) PyTorch MPS 지원 LoRA SFT 학습 스크립트
Framework: Hugging Face transformers + trl (SFTTrainer) + peft
Target Model: Qwen/Qwen2.5-3B-Instruct
Dataset: data/sft/train.jsonl (130개) & data/sft/valid.jsonl (20개)
"""

import os
import torch
from datasets import load_dataset
from transformers import AutoModelForCausalLM, AutoTokenizer, TrainingArguments
from trl import SFTTrainer
from peft import LoraConfig, get_peft_model

def get_device():
    if torch.backends.mps.is_available():
        return "mps"
    elif torch.cuda.is_available():
        return "cuda"
    return "cpu"

def main():
    device = get_device()
    print("=" * 60)
    print(f" 🍏 M4 Mac LoRA SFT 파인튜닝 시작 (실행 디바이스: {device})")
    print("=" * 60)

    model_id = "Qwen/Qwen2.5-3B-Instruct"
    output_dir = "./output/m4-sft-lora-final"

    # 1. 토크나이저 및 모델 로드
    print(f"[1/4] 모델 로드 중: {model_id}...")
    tokenizer = AutoTokenizer.from_pretrained(model_id, trust_remote_code=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    dtype = torch.bfloat16 if device in ["mps", "cuda"] else torch.float32

    model = AutoModelForCausalLM.from_pretrained(
        model_id,
        torch_dtype=dtype,
        device_map=device if device != "mps" else None,
        trust_remote_code=True
    )
    if device == "mps":
        model = model.to("mps")

    # 2. LoRA 어댑터 설정
    peft_config = LoraConfig(
        r=16,
        lora_alpha=32,
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
        lora_dropout=0.05,
        bias="none",
        task_type="CAUSAL_LM"
    )

    # 3. 데이터셋 로드
    print("[2/4] SFT 데이터셋 로드 중 (130 train, 20 valid)...")
    dataset = load_dataset("json", data_files={
        "train": "data/sft/train.jsonl",
        "validation": "data/sft/valid.jsonl"
    })

    # 4. 학습 인자 설정
    training_args = TrainingArguments(
        output_dir=output_dir,
        num_train_epochs=3,
        per_device_train_batch_size=2,
        per_device_eval_batch_size=2,
        gradient_accumulation_steps=4,
        learning_rate=2e-4,
        lr_scheduler_type="cosine",
        warmup_ratio=0.1,
        logging_steps=5,
        eval_strategy="epoch",
        save_strategy="epoch",
        save_total_limit=2,
        load_best_model_at_end=True,
        metric_for_best_model="loss",
        report_to="none"
    )

    print("[3/4] SFTTrainer 초기화 및 LoRA 적용...")
    trainer = SFTTrainer(
        model=model,
        args=training_args,
        train_dataset=dataset["train"],
        eval_dataset=dataset["validation"],
        peft_config=peft_config,
    )

    print("[4/4] 파인튜닝 실행 시작...")
    trainer.train()

    print(f"\n✔ 학습 완료! 최종 어댑터 저장 중: {output_dir}")
    trainer.model.save_pretrained(output_dir)
    tokenizer.save_pretrained(output_dir)
    print("=" * 60)
    print(" 🎉 M4 LoRA SFT 학습이 성공적으로 완료되었습니다!")
    print("=" * 60)

if __name__ == "__main__":
    main()
