import json
from pathlib import Path

# 다계층 통합 랩(Multi-tier Redundant Topology) 전용 신규 30개 시나리오
multitier_scenarios = [
    # 1. Core Redundancy & Load Balancing (8)
    {
        "scenario_id": "MULTITIER_CORE_ROOT_PRIMARY_01",
        "task_description": "[목표 지향형] VLAN 10의 메인 게이트웨이 트래픽을 집중시키기 위해 Core-1(core-sw1)을 Root Primary로 선출되도록 구성하세요.",
        "target_node": "core-sw1",
        "vlan_id": 10,
        "current_state": "Core-2가 임시 루트 상태",
        "expected_root_node": "core-sw1",
        "verify_command": "show spanning-tree vlan 10",
        "baseline_commands": ["spanning-tree vlan 10 root primary"],
        "convergence_wait_seconds": 3.0
    },
    {
        "scenario_id": "MULTITIER_CORE_ROOT_SECONDARY_02",
        "task_description": "[장애 대응형] Core-1 장애 발생 시 무중단 인계를 위해 Core-2(core-sw2)를 VLAN 10의 백업 루트(Root Secondary)로 지정하세요.",
        "target_node": "core-sw2",
        "vlan_id": 10,
        "current_state": "Core-2 기본 우선순위(32768)",
        "expected_root_node": "core-sw1",
        "verify_command": "show spanning-tree vlan 10",
        "baseline_commands": ["spanning-tree vlan 10 root secondary"],
        "convergence_wait_seconds": 3.0
    },
    {
        "scenario_id": "MULTITIER_PER_VLAN_BALANCING_03",
        "task_description": "[트래픽 엔지니어링] Core-1과 Core-2의 L2 대역폭 부하를 분산하기 위해 VLAN 20은 Core-2가 Root Primary를 담당하도록 구성하세요.",
        "target_node": "core-sw2",
        "vlan_id": 20,
        "current_state": "모든 VLAN이 Core-1에 집중됨",
        "expected_root_node": "core-sw2",
        "verify_command": "show spanning-tree vlan 20",
        "baseline_commands": ["spanning-tree vlan 20 priority 4096"],
        "convergence_wait_seconds": 3.0
    },
    {
        "scenario_id": "MULTITIER_CORE_INTERCONNECT_PO_04",
        "task_description": "[인프라 확장형] Core-1과 Core-2 간의 이중 링크(Ethernet0/0, Ethernet0/1)를 LACP 액티브 Port-Channel 1로 번들링하세요.",
        "target_node": "core-sw1",
        "vlan_id": 1,
        "current_state": "독립 물리 이중 링크 상태",
        "expected_root_node": "core-sw1",
        "verify_command": "show etherchannel summary",
        "baseline_commands": ["interface range Ethernet0/0 - 1", "channel-group 1 mode active"],
        "convergence_wait_seconds": 4.0
    },
    {
        "scenario_id": "MULTITIER_CORE_PO_COST_05",
        "task_description": "[경로 최적화] Core 간 번들 링크(Port-channel 1)의 STP Cost를 3으로 낮추어 Core 간 경로를 최우선 고속 백본으로 지정하세요.",
        "target_node": "core-sw1",
        "vlan_id": 1,
        "current_state": "기본 Cost",
        "expected_root_node": "core-sw1",
        "target_interface": "Port-channel 1",
        "verify_command": "show spanning-tree vlan 1",
        "baseline_commands": ["interface Port-channel 1", "spanning-tree cost 3"],
        "convergence_wait_seconds": 3.0
    },
    {
        "scenario_id": "MULTITIER_CORE_UNSET_ROOT_06",
        "task_description": "[롤백형] Core-1에 적용된 VLAN 10 Root Primary 설정을 해제하고 기본 우선순위(32768)로 복원하세요.",
        "target_node": "core-sw1",
        "vlan_id": 10,
        "current_state": "Core-1이 Root Primary 상태",
        "expected_root_node": "core-sw2",
        "verify_command": "show spanning-tree vlan 10",
        "baseline_commands": ["no spanning-tree vlan 10 priority"],
        "convergence_wait_seconds": 3.0
    },
    {
        "scenario_id": "MULTITIER_CORE_UNSET_PO_07",
        "task_description": "[원복형] Core-1의 Ethernet0/0, Ethernet0/1에 적용된 channel-group 1 번들 구성을 해제하세요.",
        "target_node": "core-sw1",
        "vlan_id": 1,
        "current_state": "Port-Channel 1 번들 활성화됨",
        "expected_root_node": "core-sw1",
        "verify_command": "show etherchannel summary",
        "baseline_commands": ["interface range Ethernet0/0 - 1", "no channel-group 1"],
        "convergence_wait_seconds": 4.0
    },
    {
        "scenario_id": "MULTITIER_CORE_UNSET_PO_IF_08",
        "task_description": "[완전 삭제형] Core-1의 Port-channel 1 논리 인터페이스를 삭제하여 초기 클린 상태로 되돌리세요.",
        "target_node": "core-sw1",
        "vlan_id": 1,
        "current_state": "Port-channel 1 인터페이스 존재",
        "expected_root_node": "core-sw1",
        "verify_command": "show etherchannel summary",
        "baseline_commands": ["no interface Port-channel 1"],
        "convergence_wait_seconds": 3.0
    },

    # 2. Multi-hop Cumulative Cost & Path Tuning (8)
    {
        "scenario_id": "MULTITIER_ACC1_UPLINK_COST_TUNING_09",
        "task_description": "[트래픽 엔지니어링] Access-1(acc-sw1)에서 Dist-2 방향 업링크(Ethernet0/1) Cost를 500으로 높여, 모든 상향 트래픽이 Dist-1으로만 전송되도록 유도하세요.",
        "target_node": "acc-sw1",
        "vlan_id": 1,
        "current_state": "Dist-1과 Dist-2 동일 Cost 19",
        "expected_root_node": "core-sw1",
        "target_interface": "Ethernet0/1",
        "verify_command": "show spanning-tree vlan 1",
        "baseline_commands": ["interface Ethernet0/1", "spanning-tree cost 500"],
        "convergence_wait_seconds": 3.0
    },
    {
        "scenario_id": "MULTITIER_DIST1_PORT_PRIO_10",
        "task_description": "[타이브레이커 제어] Dist-1(dist-sw1)에서 Access-1으로 향하는 다운링크 포트 우선순위를 64로 낮추어 다운스트림 포트 경합 시 우선 지정되도록 하세요.",
        "target_node": "dist-sw1",
        "vlan_id": 1,
        "current_state": "기본 우선순위 128",
        "expected_root_node": "core-sw1",
        "target_interface": "Ethernet0/3",
        "verify_command": "show spanning-tree vlan 1",
        "baseline_commands": ["interface Ethernet0/3", "spanning-tree port-priority 64"],
        "convergence_wait_seconds": 3.0
    },
    {
        "scenario_id": "MULTITIER_PATHCOST_METHOD_LONG_11",
        "task_description": "[고속 대역폭 지원] Core 및 Dist 계층 전체의 10G/40G 이더넷 식별을 위해 32-bit Pathcost Method Long을 전역 적용하세요.",
        "target_node": "core-sw1",
        "vlan_id": 1,
        "current_state": "기본 Short(16-bit) 모드",
        "expected_root_node": "core-sw1",
        "verify_command": "show spanning-tree summary",
        "baseline_commands": ["spanning-tree pathcost method long"],
        "convergence_wait_seconds": 3.0
    },
    {
        "scenario_id": "MULTITIER_UNSET_ACC1_COST_12",
        "task_description": "[복구형] Access-1의 Ethernet0/1 포트에 부여된 Cost 500 설정을 제거하여 기본 홉 비용으로 복원하세요.",
        "target_node": "acc-sw1",
        "vlan_id": 1,
        "current_state": "Cost 500 설정 상태",
        "expected_root_node": "core-sw1",
        "target_interface": "Ethernet0/1",
        "verify_command": "show spanning-tree vlan 1",
        "baseline_commands": ["interface Ethernet0/1", "no spanning-tree cost"],
        "convergence_wait_seconds": 3.0
    },
    {
        "scenario_id": "MULTITIER_UNSET_DIST1_PRIO_13",
        "task_description": "[복구형] Dist-1의 Ethernet0/3 인터페이스 우선순위(64)를 제거하여 기본값(128)으로 복구하세요.",
        "target_node": "dist-sw1",
        "vlan_id": 1,
        "current_state": "포트 우선순위 64 설정됨",
        "expected_root_node": "core-sw1",
        "target_interface": "Ethernet0/3",
        "verify_command": "show spanning-tree vlan 1",
        "baseline_commands": ["interface Ethernet0/3", "no spanning-tree port-priority"],
        "convergence_wait_seconds": 3.0
    },
    {
        "scenario_id": "MULTITIER_UNSET_PATHCOST_LONG_14",
        "task_description": "[원복형] Core-1의 Pathcost 모드를 기본 16-bit Short 모드로 복귀시키세요.",
        "target_node": "core-sw1",
        "vlan_id": 1,
        "current_state": "Long 모드 활성화됨",
        "expected_root_node": "core-sw1",
        "verify_command": "show spanning-tree summary",
        "baseline_commands": ["spanning-tree pathcost method short"],
        "convergence_wait_seconds": 3.0
    },
    {
        "scenario_id": "MULTITIER_DIST_INTERCONNECT_TRUNK_15",
        "task_description": "[트렁크 구성] Dist-1의 Dist-2 연동 포트(Ethernet0/2)를 802.1Q 트렁크 모드로 지정하세요.",
        "target_node": "dist-sw1",
        "vlan_id": 1,
        "current_state": "기본 Access 상태",
        "expected_root_node": "core-sw1",
        "target_interface": "Ethernet0/2",
        "verify_command": "show interfaces Ethernet0/2 trunk",
        "baseline_commands": ["interface Ethernet0/2", "switchport mode trunk"],
        "convergence_wait_seconds": 3.0
    },
    {
        "scenario_id": "MULTITIER_UNSET_DIST_TRUNK_16",
        "task_description": "[원복형] Dist-1의 Ethernet0/2 포트 트렁크 구성을 해제하고 기본 모드로 되돌리세요.",
        "target_node": "dist-sw1",
        "vlan_id": 1,
        "current_state": "트렁크 동작 중",
        "expected_root_node": "core-sw1",
        "target_interface": "Ethernet0/2",
        "verify_command": "show interfaces Ethernet0/2 trunk",
        "baseline_commands": ["interface Ethernet0/2", "switchport mode access"],
        "convergence_wait_seconds": 3.0
    },

    # 3. Security, TCN Suppression & Loop Guard in Multi-tier (8)
    {
        "scenario_id": "MULTITIER_ROOT_GUARD_DIST_17",
        "task_description": "[보안 방어형] 하위 Access 스위치나 비인가 장비가 Core의 루트 지위를 탈취하지 못하도록 Dist-1의 다운링크(Ethernet0/3)에 Root Guard를 활성화하세요.",
        "target_node": "dist-sw1",
        "vlan_id": 1,
        "current_state": "Root Guard 미설정",
        "expected_root_node": "core-sw1",
        "target_interface": "Ethernet0/3",
        "verify_command": "show spanning-tree interface Ethernet0/3 detail",
        "baseline_commands": ["interface Ethernet0/3", "spanning-tree guard root"],
        "convergence_wait_seconds": 3.0
    },
    {
        "scenario_id": "MULTITIER_LOOP_GUARD_DIST_18",
        "task_description": "[단방향 장애 방어] 단방향 링크 장애로 인한 Alternate 포트의 비정상 FWD 전이를 막기 위해 Dist-1의 업링크에 Loop Guard를 설정하세요.",
        "target_node": "dist-sw1",
        "vlan_id": 1,
        "current_state": "Loop Guard 미설정",
        "expected_root_node": "core-sw1",
        "target_interface": "Ethernet0/0",
        "verify_command": "show spanning-tree interface Ethernet0/0 detail",
        "baseline_commands": ["interface Ethernet0/0", "spanning-tree guard loop"],
        "convergence_wait_seconds": 3.0
    },
    {
        "scenario_id": "MULTITIER_BPDU_GUARD_ACC_19",
        "task_description": "[단말 보안] Access-1의 호스트 단말 연결 포트(Ethernet1/0)에 BPDU 수신 시 즉시 차단되도록 BPDU Guard를 활성화하세요.",
        "target_node": "acc-sw1",
        "vlan_id": 1,
        "current_state": "BPDU Guard 미설정",
        "expected_root_node": "core-sw1",
        "target_interface": "Ethernet1/0",
        "verify_command": "show spanning-tree interface Ethernet1/0 detail",
        "baseline_commands": ["interface Ethernet1/0", "spanning-tree bpduguard enable"],
        "convergence_wait_seconds": 3.0
    },
    {
        "scenario_id": "MULTITIER_TCN_SUPPRESS_EDGE_20",
        "task_description": "[망 안정화] PC 부팅 시 불필요한 TCN이 Core 계층까지 플러딩되지 않도록 Access-1의 전역 PortFast Edge 기본 설정을 활성화하세요.",
        "target_node": "acc-sw1",
        "vlan_id": 1,
        "current_state": "전역 Edge 비활성화",
        "expected_root_node": "core-sw1",
        "verify_command": "show spanning-tree summary",
        "baseline_commands": ["spanning-tree portfast edge default"],
        "convergence_wait_seconds": 3.0
    },
    {
        "scenario_id": "MULTITIER_BRIDGE_ASSURANCE_CORE_21",
        "task_description": "[백본 보호] Core-1과 Core-2 간 트렁크에서 양방향 BPDU 킵얼라이브를 감시하도록 전역 Bridge Assurance(PortFast Network)를 활성화하세요.",
        "target_node": "core-sw1",
        "vlan_id": 1,
        "current_state": "Network default 미설정",
        "expected_root_node": "core-sw1",
        "verify_command": "show spanning-tree summary",
        "baseline_commands": ["spanning-tree portfast network default"],
        "convergence_wait_seconds": 3.0
    },
    {
        "scenario_id": "MULTITIER_UNSET_ROOT_GUARD_22",
        "task_description": "[원복형] Dist-1의 Ethernet0/3에 설정된 Root Guard를 해제하세요.",
        "target_node": "dist-sw1",
        "vlan_id": 1,
        "current_state": "Root Guard 동작 중",
        "expected_root_node": "core-sw1",
        "target_interface": "Ethernet0/3",
        "verify_command": "show spanning-tree interface Ethernet0/3 detail",
        "baseline_commands": ["interface Ethernet0/3", "no spanning-tree guard root"],
        "convergence_wait_seconds": 3.0
    },
    {
        "scenario_id": "MULTITIER_UNSET_LOOP_GUARD_23",
        "task_description": "[원복형] Dist-1의 Ethernet0/0에 적용된 Loop Guard 구성을 제거하세요.",
        "target_node": "dist-sw1",
        "vlan_id": 1,
        "current_state": "Loop Guard 동작 중",
        "expected_root_node": "core-sw1",
        "target_interface": "Ethernet0/0",
        "verify_command": "show spanning-tree interface Ethernet0/0 detail",
        "baseline_commands": ["interface Ethernet0/0", "no spanning-tree guard loop"],
        "convergence_wait_seconds": 3.0
    },
    {
        "scenario_id": "MULTITIER_UNSET_TCN_EDGE_24",
        "task_description": "[원복형] Access-1의 전역 PortFast Edge 기본 설정을 비활성화하세요.",
        "target_node": "acc-sw1",
        "vlan_id": 1,
        "current_state": "전역 Edge 활성화됨",
        "expected_root_node": "core-sw1",
        "verify_command": "show spanning-tree summary",
        "baseline_commands": ["no spanning-tree portfast edge default"],
        "convergence_wait_seconds": 3.0
    },

    # 4. Multi-tier MSTP Region & Cross-tier Synchronization (6)
    {
        "scenario_id": "MULTITIER_MST_CORE_REGION_25",
        "task_description": "[MSTP 통합] Core-1에서 Multi-tier 백본용 MST Region 이름을 'ENTERPRISE-CORE', Revision 번호를 2로 구성하세요.",
        "target_node": "core-sw1",
        "vlan_id": 1,
        "current_state": "MST 미구성",
        "expected_root_node": "core-sw1",
        "verify_command": "show spanning-tree mst configuration",
        "baseline_commands": ["spanning-tree mst configuration", "name ENTERPRISE-CORE", "revision 2"],
        "convergence_wait_seconds": 7.0
    },
    {
        "scenario_id": "MULTITIER_MST_INSTANCE_MAP_26",
        "task_description": "[VLAN 분할] Core-1의 MST Configuration 모드에서 Instance 1에 VLAN 10-20, Instance 2에 VLAN 30-40을 매핑하세요.",
        "target_node": "core-sw1",
        "vlan_id": 10,
        "current_state": "기본 Instance 0(CST)",
        "expected_root_node": "core-sw1",
        "verify_command": "show spanning-tree mst configuration",
        "baseline_commands": ["spanning-tree mst configuration", "instance 1 vlan 10-20", "instance 2 vlan 30-40"],
        "convergence_wait_seconds": 7.0
    },
    {
        "scenario_id": "MULTITIER_MST_ROOT_PRIMARY_27",
        "task_description": "[MST 루트] Core-1을 MST Instance 1의 Root Primary 브리지로 지정하세요.",
        "target_node": "core-sw1",
        "vlan_id": 1,
        "current_state": "기본 우선순위 32768",
        "expected_root_node": "core-sw1",
        "verify_command": "show spanning-tree mst 1",
        "baseline_commands": ["spanning-tree mst 1 root primary"],
        "convergence_wait_seconds": 7.0
    },
    {
        "scenario_id": "MULTITIER_MST_CORE2_INSTANCE2_28",
        "task_description": "[부하 분산] Core-2(core-sw2)를 MST Instance 2의 Root Primary로 선출되도록 구성하여 인스턴스별 L2 트래픽을 양분하세요.",
        "target_node": "core-sw2",
        "vlan_id": 1,
        "current_state": "기본 우선순위 32768",
        "expected_root_node": "core-sw2",
        "verify_command": "show spanning-tree mst 2",
        "baseline_commands": ["spanning-tree mst 2 root primary"],
        "convergence_wait_seconds": 7.0
    },
    {
        "scenario_id": "MULTITIER_UNSET_MST_MAP_29",
        "task_description": "[원복형] Core-1의 MST Instance 1, 2 매핑 설정을 제거하여 기본 CST로 복원하세요.",
        "target_node": "core-sw1",
        "vlan_id": 10,
        "current_state": "Instance 1, 2 매핑됨",
        "expected_root_node": "core-sw1",
        "verify_command": "show spanning-tree mst configuration",
        "baseline_commands": ["spanning-tree mst configuration", "no instance 1", "no instance 2"],
        "convergence_wait_seconds": 7.0
    },
    {
        "scenario_id": "MULTITIER_UNSET_MST_REGION_30",
        "task_description": "[원복형] Core-1의 MST Configuration 모드에서 Region 이름 설정을 제거하세요.",
        "target_node": "core-sw1",
        "vlan_id": 1,
        "current_state": "Region 이름 설정됨",
        "expected_root_node": "core-sw1",
        "verify_command": "show spanning-tree mst configuration",
        "baseline_commands": ["spanning-tree mst configuration", "no name"],
        "convergence_wait_seconds": 7.0
    }
]

# 기존 120개 로드
with open("data/grpo_initial_scenario_120.json", "r", encoding="utf-8") as f:
    orig_120 = json.load(f)

# 150개 다계층 통합 시나리오 저장
all_150 = orig_120 + multitier_scenarios
out_path = Path("data/grpo_scenario_multitier_150.json")
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(all_150, f, indent=2, ensure_ascii=False)

print(f"Successfully generated {len(all_150)} scenarios (120 Unit + 30 Multi-tier Integration) -> {out_path}")
