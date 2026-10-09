import json

with open("scratch/analysis_report.json") as f:
    data = json.load(f)

type1 = [d for d in data if d["type"] == "VALID_ALTERNATIVE_SCORED_ZERO"]
type2 = [d for d in data if d["type"] == "NO_SUCCESS_CANDIDATE"]

print(f"=== 분석 요약 ===")
print(f"1. 유효한 대안(또는 더 적합한 명령)이 0점 처리되고 다른 명령만 200점인 시나리오: {len(type1)}개")
print(f"2. 성공(200점)이 전혀 없어 정답 신호가 실종된 시나리오: {len(type2)}개")

print("\n--- [유형 1: 대안 0점 처리 사례 상세 (전체)] ---")
for idx, d in enumerate(type1, 1):
    print(f"\n[{idx}] {d['scenario_id']}")
    print(f"  - 질문(Prompt): {d['prompt']}")
    print(f"  - 0점(INEFFECTIVE) 처리된 유효 대안: {d['ineffective_cmds']}")
    print(f"  - 200점(SUCCESS) 인정된 명령어: {d['success_cmds']}")

print("\n--- [유형 2: 성공(200점) 부재 사례 상위 10개] ---")
for idx, d in enumerate(type2[:10], 1):
    print(f"\n[{idx}] {d['scenario_id']}")
    print(f"  - 질문(Prompt): {d['prompt']}")
    print(f"  - 시도된 명령어: {d['outputs'][:2]}")
    print(f"  - 보상: {d['rewards']}")
