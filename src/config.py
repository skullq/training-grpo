from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any, Optional


@dataclass
class LabNode:
    """Containerlab 노드 접속 정보"""
    host: str = "127.0.0.1"
    port: int = 22
    auth_username: str = "admin"
    auth_password: str = "admin"
    auth_strict_key: bool = False
    platform: str = "cisco_iosxe"  # cisco_iosxe, arista_eos 등


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
