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

        # 3. 루트 브리지 달성 여부 확인
        is_root = bool(re.search(self.ROOT_BRIDGE_PATTERN, show_output, re.IGNORECASE))
        if is_root:
            return EvaluationResult(
                candidate_id=candidate.candidate_id,
                lab_id=lab_id,
                output_text=output_repr,
                status="SUCCESS",
                raw_reward=self.success_reward,
                error_message=None,
                is_root_bridge=True,
                raw_show_output=show_output
            )
        else:
            return EvaluationResult(
                candidate_id=candidate.candidate_id,
                lab_id=lab_id,
                output_text=output_repr,
                status="INEFFECTIVE",
                raw_reward=self.ineffective_reward,
                error_message="Configuration did not change root bridge",
                is_root_bridge=False,
                raw_show_output=show_output
            )
