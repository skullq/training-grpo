import json
from pathlib import Path

scenario_file = Path("data/grpo_initial_scenario_120.json")
with open(scenario_file, "r", encoding="utf-8") as f:
    scenarios = json.load(f)

updated_count = 0

for sc in scenarios:
    sid = sc.get("scenario_id", "")
    cmds = " ".join(sc.get("baseline_commands", [])).lower()
    desc = sc.get("task_description", "").lower()

    # 1. Spanning-tree mode pvst (802.1D 표준 Forward Delay 15s+15s = 30s)
    if "mode pvst" in cmds or "mode pvst" in desc:
        sc["convergence_wait_seconds"] = 32.0
        updated_count += 1
    # 2. MST 모드 관련 (MST 초기 수렴 7초)
    elif "mode mst" in cmds or "mode mst" in desc or sid.startswith("MST_") or sid.startswith("UNSET_MST_"):
        sc["convergence_wait_seconds"] = 7.0
        updated_count += 1
    # 3. Port-Channel (번들 생성 및 포트 결합 4초)
    elif "channel-group" in cmds or "port-channel" in cmds or sid.startswith("PORT_CHANNEL_") or sid.startswith("UNSET_PORT_CHANNEL_"):
        sc["convergence_wait_seconds"] = 4.0
        updated_count += 1
    # 4. Rapid-PVST+ 모드 명시적 원복/전환 (4초)
    elif "mode rapid-pvst" in cmds or "mode rapid-pvst" in desc:
        sc["convergence_wait_seconds"] = 4.0
        updated_count += 1
    # 5. 일반 Rapid-PVST+ 포트/우선순위 변경 등 (기본 3초)
    else:
        sc["convergence_wait_seconds"] = 3.0

with open(scenario_file, "w", encoding="utf-8") as f:
    json.dump(scenarios, f, indent=2, ensure_ascii=False)

print(f"Total scenarios: {len(scenarios)}")
print(f"Updated convergence_wait_seconds for all scenarios.")

# 분포 출력
from collections import Counter
counts = Counter(sc["convergence_wait_seconds"] for sc in scenarios)
for k, v in sorted(counts.items()):
    print(f"  - {k}s wait: {v} scenarios")
