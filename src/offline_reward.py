import re
from typing import List, Tuple, Dict, Any

class OfflineNetworkRewardEvaluator:
    """
    맥북 M4 등 외부 가상 랩(Containerlab/IOL) 연결이 불가능한 로컬 환경에서
    Cisco IOS L2/STP 도메인 문법 및 시나리오 목표를 정밀 채점하는 독립형 보상 엔진.
    Hugging Face TRL GRPOTrainer의 reward_funcs로 직접 등록 가능.
    """

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

    def parse_completion(self, text: str) -> Tuple[str, List[str], bool]:
        """
        모델의 생성 텍스트에서 <think>와 <commands>를 파싱.
        형식 위반 시 is_format_error = True
        """
        think_match = re.search(r"<think>(.*?)</think>", text, re.DOTALL)
        cmd_match = re.search(r"<commands>(.*?)</commands>", text, re.DOTALL)

        if not cmd_match:
            # 마크다운 코드블록 백업 파싱
            code_match = re.search(r"```(?:cisco|bash)?(.*?)```", text, re.DOTALL)
            if code_match:
                cmd_raw = code_match.group(1).strip()
            else:
                return "", [], True  # 태그 없음 = FORMAT_ERROR
        else:
            cmd_raw = cmd_match.group(1).strip()

        commands = [line.strip() for line in cmd_raw.splitlines() if line.strip() and not line.strip().startswith("!")]
        
        # 순수 한국어 설명문이거나 명령어가 없는 경우
        if not commands or any("입니다" in c or "완료" in c or "설정하세요" in c for c in commands):
            return "", [], True

        thinking = think_match.group(1).strip() if think_match else ""
        return thinking, commands, False

    def validate_syntax(self, commands: List[str]) -> Tuple[bool, str]:
        """Cisco L2/STP 도메인 문법 정적 검증"""
        for cmd in commands:
            c = cmd.lower()
            if "invalid" in c or "error" in c:
                return False, "% Invalid parameter detected"

            # 1. Bridge Priority: 0~61440 및 4096의 배수
            prio_match = re.search(r"priority\s+(\d+)", c)
            if prio_match:
                val = int(prio_match.group(1))
                if val < 0 or val > 61440 or val % 4096 != 0:
                    return False, f"% Parameter value {val} is not valid; must be in increments of 4096 (0-61440)"

            # 2. Port Priority: 0~240 및 16의 배수
            port_prio_match = re.search(r"port-priority\s+(\d+)", c)
            if port_prio_match:
                val = int(port_prio_match.group(1))
                if val < 0 or val > 240 or val % 16 != 0:
                    return False, f"% Parameter value {val} is not valid; must be in increments of 16 (0-240)"

            # 3. Path Cost: 1~200,000,000
            cost_match = re.search(r"cost\s+(\d+)", c)
            if cost_match and "pathcost" not in c:
                val = int(cost_match.group(1))
                if val < 1 or val > 200000000:
                    return False, f"% Parameter value {val} is not valid; cost out of range"

        return True, "Valid syntax"

    def evaluate_response(self, completion: str, scenario: Dict[str, Any]) -> Tuple[float, str]:
        """
        단일 생성물에 대한 최종 점수 및 상태 산출
        Returns: (reward, status)
        """
        thinking, commands, is_format_error = self.parse_completion(completion)
        if is_format_error or not commands:
            return self.format_error_reward, "FORMAT_ERROR"

        is_valid_syntax, err_msg = self.validate_syntax(commands)
        if not is_valid_syntax:
            return self.syntax_error_reward, "SYNTAX_ERROR"

        # 시나리오 baseline과의 의미적 동치성 검증
        base_cmds = scenario.get("baseline_commands", [])
        cand_text = " \n ".join(commands).lower()
        base_text = " \n ".join(base_cmds).lower()

        # 정규화된 키워드 일치성 검사
        from src.interface_normalizer import normalize_interface_name
        
        # 완전 일치 또는 의미적 성공 검증
        norm_cand = re.sub(r"\s+", " ", cand_text).strip()
        norm_base = re.sub(r"\s+", " ", base_text).strip()

        if norm_cand == norm_base:
            return self.success_reward, "SUCCESS"

        # 루트 설정 대안 (root primary vs priority 4096 등)
        if "root primary" in base_text and ("root primary" in cand_text or "priority 4096" in cand_text or "priority 0" in cand_text):
            return self.success_reward, "SUCCESS"
        if "priority 4096" in base_text and ("priority 4096" in cand_text or "root primary" in cand_text):
            return self.success_reward, "SUCCESS"

        # 롤백 명령어 동치성 (no 구문 포함 여부)
        if any(w in scenario.get("task_description", "") for w in ["제거", "취소", "원복", "초기화"]):
            if any(c.startswith("no ") or "no " in c for c in commands):
                return self.success_reward, "SUCCESS"

        # 축약형 인터페이스 처리
        norm_cand_clean = re.sub(r"(ethernet|gigabitethernet|fastethernet|et|gi|fa)", "et", norm_cand)
        norm_base_clean = re.sub(r"(ethernet|gigabitethernet|fastethernet|et|gi|fa)", "et", norm_base)
        if norm_cand_clean == norm_base_clean:
            return self.success_reward, "SUCCESS"

        # 그 외 문법은 유효하나 목표 미달성
        return self.ineffective_reward, "INEFFECTIVE"


# Hugging Face TRL GRPOTrainer 용 보상 함수 래퍼
def trl_reward_func(completions, scenarios=None, **kwargs):
    """
    TRL GRPOTrainer(reward_funcs=[trl_reward_func]) 표준 규격 인터페이스
    """
    evaluator = OfflineNetworkRewardEvaluator()
    rewards = []
    for idx, comp in enumerate(completions):
        sc = scenarios[idx] if scenarios and idx < len(scenarios) else {}
        reward, _ = evaluator.evaluate_response(comp, sc)
        rewards.append(reward)
    return rewards
