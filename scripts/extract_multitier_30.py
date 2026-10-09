import json

with open("data/grpo_scenario_multitier_150.json", "r", encoding="utf-8") as f:
    scenarios = json.load(f)

multitier_30 = [s for s in scenarios if s.get("scenario_id", "").startswith("MULTITIER_")]

with open("data/grpo_scenario_multitier_30.json", "w", encoding="utf-8") as f:
    json.dump(multitier_30, f, indent=2, ensure_ascii=False)

print(f"Extracted {len(multitier_30)} multitier scenarios to data/grpo_scenario_multitier_30.json")
