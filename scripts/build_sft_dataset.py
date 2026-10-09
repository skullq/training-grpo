import json
from pathlib import Path
from src.interface_normalizer import normalize_interface_name

def generate_tailored_cot(scenario: dict, cmd_text: str) -> str:
    task_desc = scenario.get("task_description", "")
    current_state = scenario.get("current_state", "기본 상태")
    target_node = scenario.get("target_node", "스위치")
    vlan_id = scenario.get("vlan_id", 1)
    cmd_lower = cmd_text.lower()

    # Step 1: 토폴로지 분석
    step1 = f"1. 토폴로지 분석: 대상 장비는 '{target_node}'이며, 현재 L2 상태는 '{current_state}'임. 목표는 '{task_desc}' 요구사항을 정확히 충족하는 것임."

    # Step 2: 파라미터 및 타이브레이커 계산
    if "no name" in cmd_lower or "no instance" in cmd_lower:
        step2 = "2. 파라미터 및 타이브레이커 계산: MST Configuration 서브모드에 진입하여 기존에 등록된 Region 이름 또는 Instance 매핑을 'no' 구문으로 안전하게 제거하고 공장 기본 CST 동작으로 원복함."
    elif "no " in cmd_lower or "mode access" in cmd_lower or "portfast normal" in cmd_lower:
        step2 = "2. 파라미터 및 타이브레이커 계산: 기존에 적용된 수동 설정을 안전하게 원복(Rollback)하기 위해 해당 기능의 부정(no) 명령어 또는 표준 기본 모드로 복원 구문을 산출함."
    elif "root primary" in cmd_lower or "priority 0" in cmd_lower or "priority 4096" in cmd_lower or "priority 8192" in cmd_lower:
        step2 = f"2. 파라미터 및 타이브레이커 계산: VLAN {vlan_id}에 대해 Bridge Priority를 4096의 유효 배수(또는 root primary 매크로)로 낮추어 상대 스위치보다 낮은 Bridge ID(최우선 순위)를 획득함."
    elif "port-priority" in cmd_lower:
        step2 = "2. 파라미터 및 타이브레이커 계산: 하위(다운스트림) 스위치의 Root Port 선출 타이브레이커(4단계: 송신 포트 ID) 경합 시 해당 포트가 우선 선택되도록 16의 배수 규격에 맞춰 Port-Priority를 낮춤."
    elif "cost" in cmd_lower:
        step2 = "2. 파라미터 및 타이브레이커 계산: Root Path Cost 계산 공식에 따라 지정된 포트의 STP 경로 비용을 조정하여 최단 포워딩 경로 또는 차단(Alternate) 경로로 유도함."
    elif "trunk" in cmd_lower:
        step2 = "2. 파라미터 및 타이브레이커 계산: 스위치 간 고속 백본 연결을 위해 802.1Q 트렁크 인캡슐레이션을 지정하고 요구된 허용(Allowed) VLAN 리스트를 안전하게 필터링함."
    elif "guard root" in cmd_lower:
        step2 = "2. 파라미터 및 타이브레이커 계산: 하위 접속 포트로 우수한 Superior BPDU가 수신될 경우 해당 포트를 Root-Inconsistent 상태로 차단하여 루트 탈취를 방지하는 Root Guard를 적용함."
    elif "guard loop" in cmd_lower:
        step2 = "2. 파라미터 및 타이브레이커 계산: 단방향 링크 장애로 인한 비정상 루프 형성을 방지하기 위해 BPDU 미수신 시 차단 상태(Loop-Inconsistent)로 전이시키는 Loop Guard를 활성화함."
    elif "edge" in cmd_lower or "portfast" in cmd_lower:
        step2 = "2. 파라미터 및 타이브레이커 계산: 종단 단말이 연결된 엑세스 포트에서 불필요한 TCN 생성을 억제하고 즉시 Forwarding 상태로 진입하도록 표준 PortFast Edge 구문을 적용함."
    elif "channel-group" in cmd_lower or "port-channel" in cmd_lower:
        step2 = "2. 파라미터 및 타이브레이커 계산: 복수 물리 포트를 논리적 EtherChannel 번들로 묶어 L2 대역폭을 확장하고 Spanning-Tree 관점에서 단일 논리 링크로 인식되도록 그룹화함."
    elif "mst" in cmd_lower:
        step2 = "2. 파라미터 및 타이브레이커 계산: 대규모 VLAN 확장을 위해 MST Configuration 모드에서 Region/Revision/Instance 매핑을 정의하고 고유한 인스턴스별 루트 브리지를 선출함."
    else:
        step2 = f"2. 파라미터 및 타이브레이커 계산: Cisco IOS-XE 표준 Spanning-Tree 규격에 맞추어 유효한 매개변수를 정확히 산출함."

    # Step 3: 영향도 검토
    step3 = "3. 영향도(Blast Radius) 검토: 설정 주입 후 L2 토폴로지 재계산(TCN) 전파 영향을 확인하고, 트래픽 루프나 블랙홀 없는 신속하고 안정적인 수렴(Convergence)을 보장함."

    # Step 4: 명령어 도출
    step4 = f"4. 명령어 도출:\n{cmd_text}"

    return f"{step1}\n{step2}\n{step3}\n{step4}"

def main():
    scenario_path = Path("data/grpo_scenario_multitier_150.json")
    output_path = Path("data/sft_dataset_cold_start.jsonl")

    with open(scenario_path, "r", encoding="utf-8") as f:
        scenarios = json.load(f)

    # Spanning-Tree 도메인을 대표하는 5대 핵심 골든 시드 시나리오 ID
    GOLDEN_SEED_IDS = [
        "STP_ROOT_SETTING_01",    # 1. 루트 브리지 선점 (Priority 4096)
        "STP_PORT_COST_21",       # 2. 포트 경로 비용 튜닝 (Path Cost)
        "STP_GUARD_BPDU_29",      # 3. 인터페이스 보안 (BPDU Guard)
        "STP_MODE_SWITCH_17",     # 4. 고속 프로토콜 모드 전환 (Rapid-PVST+)
        "STP_UNSET_ROOT_01",      # 5. 설정 안전 롤백 및 복구 (Unset/Rollback)
    ]

    sft_records = []
    system_prompt = (
        "당신은 Cisco 엔터프라이즈 네트워크 엔지니어링 전문가입니다. "
        "주어진 네트워크 토폴로지와 L2/STP 요구사항을 정밀하게 분석하여, "
        "4단계 Chain-of-Thought 추론을 <think> 태그 안에 단계별로 작성하고, "
        "실행할 최종 Cisco CLI 명령어를 <commands> 태그 안에 순서대로 작성하세요."
    )

    for sc in scenarios:
        sc_id = sc["scenario_id"]
        if sc_id not in GOLDEN_SEED_IDS:
            continue

        task_desc = sc["task_description"]
        curr_state = sc.get("current_state", "기본 상태")
        prompt = f"{task_desc} (현재 상태: {curr_state})"

        primary_cmds = "\n".join(sc.get("baseline_commands", []))
        if primary_cmds:
            thinking = generate_tailored_cot(sc, primary_cmds)
            assistant_content = f"<think>\n{thinking}\n</think>\n<commands>\n{primary_cmds}\n</commands>"
            sft_records.append({
                "scenario_id": sc_id,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt},
                    {"role": "assistant", "content": assistant_content}
                ]
            })

    with open(output_path, "w", encoding="utf-8") as f:
        for r in sft_records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    print(f"==========================================================")
    print(f"  1단계 콜드 스타트 SFT 데이터셋 구축 완료 (골든 시드 체제)")
    print(f"==========================================================")
    print(f"총 SFT 데이터 레코드 수: {len(sft_records)}개 (STP 5대 대표 골든 시드)")
    print(f"저장 파일 경로: {output_path.resolve()} ({output_path.stat().st_size / 1024:.1f} KB)")
    print(f"포맷: Hugging Face TRL SFTTrainer 표준 Chat Messages Format")
    print(f"==========================================================")

if __name__ == "__main__":
    main()
