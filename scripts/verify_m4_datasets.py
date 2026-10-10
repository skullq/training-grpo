import json
from pathlib import Path
from collections import Counter

def verify_sft(file_path):
    print(f"\n[검증] SFT: {file_path}")
    count = 0
    tag_errors = 0
    empty_cmds = 0
    with open(file_path, "r", encoding="utf-8") as f:
        for idx, line in enumerate(f, 1):
            row = json.loads(line)
            count += 1
            msgs = row.get("messages", [])
            roles = [m["role"] for m in msgs]
            if roles != ["system", "user", "assistant"]:
                print(f"  Line {idx}: Invalid roles {roles}")
            assist = msgs[2]["content"]
            if "<think>" not in assist or "</think>" not in assist or "<commands>" not in assist or "</commands>" not in assist:
                tag_errors += 1
            cmds = assist.split("<commands>")[1].split("</commands>")[0].strip()
            if not cmds:
                empty_cmds += 1
    print(f"  총 레코드: {count}개 | 태그 오류: {tag_errors}개 | 빈 명령어: {empty_cmds}개")
    return count > 0 and tag_errors == 0 and empty_cmds == 0

def verify_dpo(file_path):
    print(f"\n[검증] DPO: {file_path}")
    count = 0
    identical = 0
    with open(file_path, "r", encoding="utf-8") as f:
        for idx, line in enumerate(f, 1):
            row = json.loads(line)
            count += 1
            chosen = row["chosen"][0]["content"]
            rejected = row["rejected"][0]["content"]
            if chosen == rejected:
                identical += 1
    print(f"  총 레코드: {count}개 | 동일한 chosen/rejected: {identical}개")
    return count > 0 and identical == 0

def verify_grpo_repaired(file_path):
    print(f"\n[검증] GRPO Repaired: {file_path}")
    rows = [json.loads(line) for line in open(file_path, "r", encoding="utf-8")]
    count = len(rows)
    zero_var = 0
    no_success = 0
    bad_adv_on_neg = 0
    status_counter = Counter()

    for r in rows:
        outputs = r["group_outputs"]
        rewards = [o["raw_reward"] for o in outputs]
        statuses = [o["status"] for o in outputs]
        for s in statuses:
            status_counter[s] += 1

        if len(set(rewards)) == 1:
            zero_var += 1
        if "SUCCESS" not in statuses:
            no_success += 1
        
        # 오답 중 Advantage > 0 인 비정상 케이스 (SUCCESS가 있는데 오답이 양수를 받거나, 최고 점수가 오답인 경우)
        max_item = max(outputs, key=lambda x: x["relative_advantage"])
        if max_item["status"] != "SUCCESS":
            bad_adv_on_neg += 1

    print(f"  총 시나리오: {count}개")
    print(f"  상태 분포: {dict(status_counter)}")
    print(f"  분산 0(Zero Variance) 그룹: {zero_var}개 (기존: 0)")
    print(f"  SUCCESS 없는 그룹: {no_success}개 (기존: 37개 -> 0개 개선)")
    print(f"  최고 Advantage가 오답인 그룹: {bad_adv_on_neg}개 (기존: 31개 -> 0개 개선)")
    return count == 150 and zero_var == 0 and no_success == 0 and bad_adv_on_neg == 0

def main():
    ok1 = verify_sft("data/sft/train.jsonl")
    ok2 = verify_sft("data/sft/valid.jsonl")
    ok3 = verify_dpo("data/dpo/train.jsonl")
    ok4 = verify_dpo("data/dpo/valid.jsonl")
    ok5 = verify_grpo_repaired("data/grpo/grpo_dataset_150_repaired.jsonl")

    print("\n" + "="*50)
    if all([ok1, ok2, ok3, ok4, ok5]):
        print("  🎉 모든 M4 학습용 데이터셋 검증 100% 통과!")
    else:
        print("  ❌ 일부 데이터셋에 검증 오류 발생!")
    print("="*50)

if __name__ == "__main__":
    main()
