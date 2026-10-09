import json
from collections import defaultdict

with open("data/grpo_dataset_all_150.jsonl") as f:
    records = [json.loads(line) for line in f]

results = []

for r in records:
    scen_id = r["scenario_id"]
    prompt = r["prompt"]
    outputs = r["group_outputs"]
    
    rewards = [o["raw_reward"] for o in outputs]
    statuses = [o["status"] for o in outputs]
    
    # 유형 1: 유효한 명령어가 0점(INEFFECTIVE)인데 다른 대안이 200점인 경우 (사용자 지적 사례)
    has_200 = any(rew == 200.0 for rew in rewards)
    ineffective_valid_cmds = []
    for o in outputs:
        if o["raw_reward"] == 0.0 and o["status"] == "INEFFECTIVE":
            cmd = o["output"]
            if any(k in cmd for k in ["spanning-tree", "switchport", "interface", "no "]):
                ineffective_valid_cmds.append(cmd)
                
    if has_200 and ineffective_valid_cmds:
        success_cmds = [o["output"] for o in outputs if o["raw_reward"] == 200.0]
        results.append({
            "type": "VALID_ALTERNATIVE_SCORED_ZERO",
            "scenario_id": scen_id,
            "prompt": prompt,
            "ineffective_cmds": ineffective_valid_cmds,
            "success_cmds": success_cmds
        })
    elif not has_200:
        # 유형 2: 200점(성공)이 아예 하나도 없는 경우
        results.append({
            "type": "NO_SUCCESS_CANDIDATE",
            "scenario_id": scen_id,
            "prompt": prompt,
            "rewards": rewards,
            "statuses": statuses,
            "outputs": [o["output"] for o in outputs]
        })

print(f"Total scenarios analyzed: {len(records)}")
print(f"Type 1 (Alternative valid CLI scored 0 while another scored 200): {len([r for r in results if r['type'] == 'VALID_ALTERNATIVE_SCORED_ZERO'])}")
print(f"Type 2 (No success candidate at all): {len([r for r in results if r['type'] == 'NO_SUCCESS_CANDIDATE'])}")

with open("scratch/analysis_report.json", "w", encoding="utf-8") as f:
    json.dump(results, f, ensure_ascii=False, indent=2)

print("Saved to scratch/analysis_report.json")
