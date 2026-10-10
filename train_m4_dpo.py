"""
Apple Silicon Mac (M4 / M4 Pro / M4 Max) PyTorch MPS 지원 LoRA DPO 선호도 정렬 스크립트
Framework: Hugging Face transformers + trl (DPOTrainer) + peft
Target Model: Qwen/Qwen2.5-3B-Instruct (또는 Stage 1 SFT 체크포인트)
Dataset: data/dpo/train.jsonl (130개) & data/dpo/valid.jsonl (20개)
"""

import os
import torch
from datasets import load_dataset
from transformers import AutoModelForCausalLM, AutoTokenizer, TrainingArguments
from trl import DPOTrainer, DPOConfig
from peft import LoraConfig

def get_device():
    if torch.backends.mps.is_available():
        return "mps"
    elif torch.cuda.is_available():
        return "cuda"
    return "cpu"

def main():
    device = get_device()
    print("=" * 60)
    print(f" 🍏 M4 Mac LoRA DPO 선호도 정렬 학습 시작 (실행 디바이스: {device})")
    print("=" * 60)

    # Stage 1 SFT 결과물이 있으면 우선 사용, 없으면 베이스 모델 사용
    sft_checkpoint = "./output/m4-sft-lora-final"
    model_id = sft_checkpoint if os.path.exists(sft_checkpoint) else "Qwen/Qwen2.5-3B-Instruct"
    output_dir = "./output/m4-dpo-lora-final"

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

    peft_config = LoraConfig(
        r=16,
        lora_alpha=32,
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
        lora_dropout=0.05,
        bias="none",
        task_type="CAUSAL_LM"
    )

    print("[2/4] DPO 선호도 데이터셋 로드 중 (130 train, 20 valid)...")
    dataset = load_dataset("json", data_files={
        "train": "data/dpo/train.jsonl",
        "validation": "data/dpo/valid.jsonl"
    })

    dpo_args = DPOConfig(
        output_dir=output_dir,
        beta=0.1,  # KL penalty 계수
        num_train_epochs=3,
        per_device_train_batch_size=2,
        per_device_eval_batch_size=2,
        gradient_accumulation_steps=4,
        learning_rate=5e-6,
        lr_scheduler_type="cosine",
        warmup_ratio=0.1,
        logging_steps=5,
        eval_strategy="epoch",
        save_strategy="epoch",
        save_total_limit=2,
        report_to="none"
    )

    print("[3/4] DPOTrainer 초기화...")
    dpo_trainer = DPOTrainer(
        model=model,
        ref_model=None,  # peft 모드 시 내부 자동 복제 참조
        args=dpo_args,
        train_dataset=dataset["train"],
        eval_dataset=dataset["validation"],
        tokenizer=tokenizer,
        peft_config=peft_config,
    )

    print("[4/4] DPO 정렬 파인튜닝 실행...")
    dpo_trainer.train()

    print(f"\n✔ DPO 학습 완료! 최종 정렬 어댑터 저장 중: {output_dir}")
    dpo_trainer.model.save_pretrained(output_dir)
    tokenizer.save_pretrained(output_dir)
    print("=" * 60)
    print(" 🎉 M4 LoRA DPO 선호도 정렬 학습이 성공적으로 완료되었습니다!")
    print("=" * 60)

if __name__ == "__main__":
    main()
