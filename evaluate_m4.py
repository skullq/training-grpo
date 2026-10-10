"""
Apple Silicon Mac (M4 / M4 Pro / M4 Max) LoRA 추론 및 오프라인 검증 스크립트
MLX 및 Hugging Face PEFT 어댑터를 모두 지원하며, 
20개 Validation 시나리오에 대해 <think> CoT 및 <commands> 정확도를 자동 채점합니다.
"""

import os
import sys
import json
import argparse
from pathlib import Path

from src.offline_reward import OfflineNetworkRewardEvaluator

SYSTEM_PROMPT = (
    "당신은 Cisco 엔터프라이즈 네트워크 엔지니어링 전문가입니다. "
    "주어진 네트워크 토폴로지와 L2/STP 요구사항을 정밀하게 분석하여, "
    "4단계 Chain-of-Thought 추론을 <think> 태그 안에 단계별로 작성하고, "
    "실행할 최종 Cisco CLI 명령어를 <commands> 태그 안에 순서대로 작성하세요."
)

def evaluate_hf(adapter_path: str, valid_data_path: str, base_model: str = "Qwen/Qwen2.5-3B-Instruct"):
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer
    from peft import PeftModel

    device = "mps" if torch.backends.mps.is_available() else "cpu"
    print(f"Loading base model: {base_model} on {device}...")
    tokenizer = AutoTokenizer.from_pretrained(base_model, trust_remote_code=True)
    dtype = torch.bfloat16 if device == "mps" else torch.float32
    model = AutoModelForCausalLM.from_pretrained(base_model, torch_dtype=dtype, trust_remote_code=True)
    
    if os.path.exists(adapter_path):
        print(f"Loading LoRA adapter: {adapter_path}...")
        model = PeftModel.from_pretrained(model, adapter_path)
    if device == "mps":
        model = model.to("mps")
    model.eval()

    evaluator = OfflineNetworkRewardEvaluator()
    scenarios = [json.loads(line) for line in open(valid_data_path, "r", encoding="utf-8")]

    print(f"\nEvaluating {len(scenarios)} validation scenarios...")
    results = []
    success_count = 0

    for idx, row in enumerate(scenarios, 1):
        sc_id = row.get("scenario_id", f"SC_{idx}")
        user_prompt = row["messages"][1]["content"] if "messages" in row else row["prompt"][1]["content"]

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt}
        ]
        text_input = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        inputs = tokenizer(text_input, return_tensors="pt").to(device)

        with torch.no_grad():
            outputs = model.generate(
                **inputs,
                max_new_tokens=512,
                temperature=0.2,
                top_p=0.9,
                pad_token_id=tokenizer.eos_token_id
            )
        response = tokenizer.decode(outputs[0][inputs.input_ids.shape[1]:], skip_special_tokens=True)

        sc_obj = {"scenario_id": sc_id, "task_description": user_prompt, "baseline_commands": []}
        reward, status = evaluator.evaluate_response(response, sc_obj)
        if status == "SUCCESS":
            success_count += 1

        print(f"[{idx:02d}/20] {sc_id:<32} | 상태: {status:<12} | 보상: {reward:+6.1f}")
        results.append({"scenario_id": sc_id, "status": status, "reward": reward, "response": response})

    acc = (success_count / len(scenarios)) * 100
    print("\n" + "=" * 50)
    print(f"  평가 결과: 정답률(SUCCESS) = {success_count}/{len(scenarios)} ({acc:.1f}%)")
    print("=" * 50)


def evaluate_mlx(adapter_path: str, valid_data_path: str, base_model: str = "Qwen/Qwen2.5-3B-Instruct"):
    from mlx_lm import load, generate

    print(f"Loading MLX model: {base_model} with adapter: {adapter_path}...")
    model, tokenizer = load(base_model, adapter_path=adapter_path)
    evaluator = OfflineNetworkRewardEvaluator()
    scenarios = [json.loads(line) for line in open(valid_data_path, "r", encoding="utf-8")]

    print(f"\nEvaluating {len(scenarios)} validation scenarios (Apple MLX Engine)...")
    success_count = 0

    for idx, row in enumerate(scenarios, 1):
        sc_id = row.get("scenario_id", f"SC_{idx}")
        user_prompt = row["messages"][1]["content"] if "messages" in row else row["prompt"][1]["content"]

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt}
        ]
        text_input = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        response = generate(model, tokenizer, prompt=text_input, max_tokens=512, temp=0.2)

        sc_obj = {"scenario_id": sc_id, "task_description": user_prompt, "baseline_commands": []}
        reward, status = evaluator.evaluate_response(response, sc_obj)
        if status == "SUCCESS":
            success_count += 1

        print(f"[{idx:02d}/20] {sc_id:<32} | 상태: {status:<12} | 보상: {reward:+6.1f}")

    acc = (success_count / len(scenarios)) * 100
    print("\n" + "=" * 50)
    print(f"  평가 결과: 정답률(SUCCESS) = {success_count}/{len(scenarios)} ({acc:.1f}%)")
    print("=" * 50)


def main():
    parser = argparse.ArgumentParser(description="M4 Mac LoRA Evaluation Tool")
    parser.add_argument("--engine", type=str, choices=["hf", "mlx"], default="hf", help="추론 엔진: hf 또는 mlx")
    parser.add_argument("--adapter", type=str, default="./output/m4-sft-lora-final", help="LoRA 어댑터 디렉토리 경로")
    parser.add_argument("--data", type=str, default="data/sft/valid.jsonl", help="평가용 데이터 파일 경로")
    parser.add_argument("--model", type=str, default="Qwen/Qwen2.5-3B-Instruct", help="베이스 모델 ID")
    args = parser.parse_args()

    if args.engine == "mlx":
        evaluate_mlx(args.adapter, args.data, args.model)
    else:
        evaluate_hf(args.adapter, args.data, args.model)

if __name__ == "__main__":
    main()
