from dataclasses import dataclass, field, asdict
import json
from pathlib import Path
from typing import List, Dict, Any, Optional, Union


@dataclass
class LabNode:
    """Containerlab 노드 접속 정보"""
    host: str = "127.0.0.1"
    port: int = 22
    auth_username: str = "admin"
    auth_password: str = "admin"
    auth_strict_key: bool = False
    platform: str = "cisco_iosxe"  # cisco_iosxe, arista_eos 등
    interface_map: Dict[str, str] = field(default_factory=dict)


@dataclass
class Scenario:
    """학습용 기초 시나리오"""
    scenario_id: str
    task_description: str
    target_node: str
    vlan_id: int = 1
    current_state: str = "SW3가 Root"
    expected_root_node: str = "SW1"
    baseline_commands: List[str] = field(default_factory=list)
    target_interface: Optional[str] = None

    def with_interface_map(self, interface_map: Dict[str, str]) -> "Scenario":
        """지정된 interface_map에 따라 프롬프트 설명 및 baseline 명령어를 치환한 새로운 Scenario 반환"""
        if not interface_map:
            return self
        from src.interface_normalizer import apply_interface_mapping_to_text, apply_interface_mapping_to_commands
        new_desc = apply_interface_mapping_to_text(self.task_description, interface_map)
        new_state = apply_interface_mapping_to_text(self.current_state, interface_map)
        new_cmds = apply_interface_mapping_to_commands(self.baseline_commands, interface_map)
        new_iface = apply_interface_mapping_to_text(self.target_interface or "", interface_map) if self.target_interface else None
        return Scenario(
            scenario_id=self.scenario_id,
            task_description=new_desc,
            target_node=self.target_node,
            vlan_id=self.vlan_id,
            current_state=new_state,
            expected_root_node=self.expected_root_node,
            baseline_commands=new_cmds,
            target_interface=new_iface or self.target_interface
        )


@dataclass
class CandidateAction:
    """Generator가 생성한 액션 후보군"""
    candidate_id: int
    thinking: str = ""
    commands: List[str] = field(default_factory=list)
    raw_response: str = ""
    is_format_error: bool = False


@dataclass
class EvaluationResult:
    """개별 랩 검증 및 점수 결과"""
    candidate_id: int
    lab_id: str
    output_text: str
    status: str  # SUCCESS, SYNTAX_ERROR, FORMAT_ERROR, INEFFECTIVE
    raw_reward: float = 0.0
    relative_advantage: float = 0.0
    error_message: Optional[str] = None
    is_root_bridge: bool = False
    raw_show_output: str = ""


@dataclass
class GroupOutputItem:
    """사용자 지정 GRPO 데이터셋 단위 출력 항목"""
    output: str
    raw_reward: float
    relative_advantage: float
    status: str


@dataclass
class GRPOScenarioRecord:
    """사용자 지정 GRPO JSONL 레코드 규격"""
    scenario_id: str
    prompt: str
    group_outputs: List[GroupOutputItem]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def load_lab_nodes(config_path: Union[str, Path]) -> Dict[str, LabNode]:
    """접속정보 JSON 파일로부터 LabNode 매핑 딕셔너리 로드
    
    지원 형식:
    1. Key-Value 맵 형태:
       {
         "clab_node_1": {"host": "127.0.0.1", "port": 2201, ...},
         ...
       }
    2. 리스트 형태:
       [
         {"id": "clab_node_1", "host": "127.0.0.1", "port": 2201, ...},
         ...
       ]
    """
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"랩 접속 정보 파일을 찾을 수 없습니다: {path.resolve()}")

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    nodes: Dict[str, LabNode] = {}
    if isinstance(data, dict):
        for node_id, node_info in data.items():
            kwargs = {k: v for k, v in node_info.items() if k in LabNode.__annotations__}
            nodes[node_id] = LabNode(**kwargs)
    elif isinstance(data, list):
        for idx, item in enumerate(data, start=1):
            node_id = item.get("id") or item.get("name") or f"clab_node_{idx}"
            kwargs = {k: v for k, v in item.items() if k in LabNode.__annotations__}
            nodes[node_id] = LabNode(**kwargs)
    else:
        raise ValueError(f"지원하지 않는 랩 설정 파일 형식입니다 (dict 또는 list 필요): {type(data)}")

    return nodes


def save_lab_nodes(labs: Dict[str, LabNode], config_path: Union[str, Path]) -> None:
    """LabNode 매핑을 JSON 파일로 저장"""
    path = Path(config_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    serialized = {k: asdict(v) for k, v in labs.items()}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(serialized, f, indent=2, ensure_ascii=False)
