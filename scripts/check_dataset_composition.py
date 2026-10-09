import json

with open('data/grpo_dataset_multitier_150.jsonl', 'r', encoding='utf-8') as f:
    lines = [json.loads(l) for l in f]

unit_count = sum(1 for l in lines if not l['scenario_id'].startswith('MULTITIER_'))
multi_count = sum(1 for l in lines if l['scenario_id'].startswith('MULTITIER_'))

print(f"Total scenarios in dataset: {len(lines)}")
print(f"  - 단층 구조 (Unit Test 3노드 랩 기반): {unit_count}개")
print(f"  - 다층 구조 (Multi-tier 6노드 통합 랩 기반): {multi_count}개")
print(f"  - 첫 번째 시나리오: {lines[0]['scenario_id']}")
print(f"  - 120번째 (단층 마지막): {lines[119]['scenario_id']}")
print(f"  - 121번째 (다층 시작): {lines[120]['scenario_id']}")
print(f"  - 150번째 (다층 마지막): {lines[-1]['scenario_id']}")
