import re
from typing import List, Tuple
from src.config import EvaluationResult, Scenario, CandidateAction


class SpanningTreeEvaluator:
    """
    네트워크 장비의 CLI 응답 및 Spanning-Tree 상태를 분석하여
    상태(Status)와 보상 점수(raw_reward)를 산출하는 평가기
    """

    ERROR_PATTERNS = [
        r"% Invalid input detected",
        r"% Incomplete command",
        r"% Ambiguous command",
        r"% Type \"show \?\" for help",
        r"% Command rejected",
        r"% Error"
    ]

    ROOT_BRIDGE_PATTERN = r"This bridge is the root"

    def __init__(
        self,
        success_reward: float = 200.0,
        syntax_error_reward: float = -150.0,
        format_error_reward: float = -200.0,
        ineffective_reward: float = 0.0
    ):
        self.success_reward = success_reward
        self.syntax_error_reward = syntax_error_reward
        self.format_error_reward = format_error_reward
        self.ineffective_reward = ineffective_reward

    def check_syntax_errors(self, execution_output: str) -> Tuple[bool, str]:
        """명령어 주입 중 발생한 CLI 문법 오류 확인"""
        for pattern in self.ERROR_PATTERNS:
            match = re.search(pattern, execution_output, re.IGNORECASE)
            if match:
                return True, match.group(0)
        return False, ""

    def evaluate_output(
        self,
        candidate: CandidateAction,
        lab_id: str,
        injection_output: str,
        show_output: str,
        scenario: Scenario
    ) -> EvaluationResult:
        """
        보상 체계 (사용자 정의 기준):
        - FORMAT_ERROR: 명령어가 아닌 한국어/일반 텍스트만 출력된 경우 -> -200
        - SYNTAX_ERROR: CLI 문법 오류 발생 -> -150
        - SUCCESS: 정상적으로 루트 브리지로 선정 -> +200
        - INEFFECTIVE: 문법은 맞으나 루트 브리지 미달성 -> 0
        """
        output_repr = "\n".join(candidate.commands) if candidate.commands else candidate.raw_response

        # 1. 포맷 에러 확인 (CLI 명령어가 없고 텍스트만 있는 경우)
        if candidate.is_format_error or not candidate.commands:
            return EvaluationResult(
                candidate_id=candidate.candidate_id,
                lab_id=lab_id,
                output_text=candidate.raw_response.strip(),
                status="FORMAT_ERROR",
                raw_reward=self.format_error_reward,
                error_message="Invalid format: expected CLI commands",
                is_root_bridge=False,
                raw_show_output=""
            )

        # 2. 문법 에러 확인
        has_error, err_msg = self.check_syntax_errors(injection_output)
        if has_error:
            return EvaluationResult(
                candidate_id=candidate.candidate_id,
                lab_id=lab_id,
                output_text=output_repr,
                status="SYNTAX_ERROR",
                raw_reward=self.syntax_error_reward,
                error_message=err_msg,
                is_root_bridge=False,
                raw_show_output=show_output
            )

        # 3. 시나리오 목적에 따른 성공 여부 판정 (Root Bridge 또는 Interface/Port 파라미터)
        is_success, success_reason = self._verify_scenario_goal(candidate, show_output, scenario)
        if is_success:
            return EvaluationResult(
                candidate_id=candidate.candidate_id,
                lab_id=lab_id,
                output_text=output_repr,
                status="SUCCESS",
                raw_reward=self.success_reward,
                error_message=None,
                is_root_bridge=("This bridge is the root" in show_output),
                raw_show_output=show_output
            )
        else:
            return EvaluationResult(
                candidate_id=candidate.candidate_id,
                lab_id=lab_id,
                output_text=output_repr,
                status="INEFFECTIVE",
                raw_reward=self.ineffective_reward,
                error_message=success_reason or "Configuration did not achieve desired STP state",
                is_root_bridge=False,
                raw_show_output=show_output
            )

    def _verify_scenario_goal(
        self, candidate: CandidateAction, show_output: str, scenario: Scenario
    ) -> Tuple[bool, str]:
        """시나리오 유형(Root Bridge 변경, Interface Cost/Priority, Guard 등)에 따른 유연한 상태 검증"""
        from src.interface_normalizer import build_interface_regex_pattern, normalize_interface_name

        # A. 루트 브리지 설정 목표 시나리오
        if "root" in scenario.task_description.lower() or "루트" in scenario.task_description:
            if re.search(self.ROOT_BRIDGE_PATTERN, show_output, re.IGNORECASE):
                return True, "Root bridge elected successfully"
            # secondary root 시나리오의 경우 우선순위가 낮아졌는지 등 확인 가능

        # B. 인터페이스 관련 시나리오 (Cost, Priority, Guard 등)
        target_if = scenario.target_interface
        if not target_if:
            # baseline_commands 또는 task_description에서 인터페이스 탐색
            all_text = " ".join(scenario.baseline_commands + [scenario.task_description])
            from src.interface_normalizer import INTERFACE_REGEX
            if_match = INTERFACE_REGEX.search(all_text)
            if if_match:
                target_if = if_match.group(0)

        if target_if:
            if_pattern = build_interface_regex_pattern(target_if)
            
            # 1) Cost 변경 검증
            cost_match = re.search(r"cost\s+(\d+)", " ".join(candidate.commands), re.IGNORECASE)
            if cost_match:
                expected_cost = cost_match.group(1)
                # show 출력에서 해당 인터페이스 라인의 Cost 확인
                # 예: Et0/0  Desg FWD 4  128.1
                cost_line_pattern = rf"{if_pattern}\s+\S+\s+\S+\s+{expected_cost}\b"
                if re.search(cost_line_pattern, show_output, re.IGNORECASE):
                    return True, f"Interface {target_if} cost changed to {expected_cost}"

            # 2) Port Priority 변경 검증
            prio_match = re.search(r"port-priority\s+(\d+)", " ".join(candidate.commands), re.IGNORECASE)
            if prio_match:
                expected_prio = prio_match.group(1)
                prio_line_pattern = rf"{if_pattern}\s+.*?{expected_prio}\.\d+"
                if re.search(prio_line_pattern, show_output, re.IGNORECASE):
                    return True, f"Interface {target_if} port priority changed to {expected_prio}"

            # 3) Guard / PortFast 검증
            if any("guard" in c.lower() or "portfast" in c.lower() for c in candidate.commands):
                if re.search(rf"{if_pattern}", show_output, re.IGNORECASE):
                    return True, f"Interface {target_if} feature configured successfully"

        # C. 모드 변경 (Rapid-PVST, MST 등)
        if "rapid-pvst" in scenario.task_description.lower() or "mst" in scenario.task_description.lower():
            if re.search(r"Spanning tree enabled protocol (rstp|mstp|ieee)", show_output, re.IGNORECASE):
                return True, "STP protocol mode switched successfully"

        # D. 기본 루트 브리지 패턴 재확인 (폴백)
        if re.search(self.ROOT_BRIDGE_PATTERN, show_output, re.IGNORECASE):
            return True, "Root bridge verified"

        return False, "Target state not verified in show output"
