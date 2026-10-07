import os
import re
from typing import List
from src.config import CandidateAction, Scenario

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None


class ActionGenerator:
    """
    LLM(GPT-4o, Claude 3.5, Llama-3-8B 등)을 호출하여
    주어진 네트워크 시나리오에 대해 5개의 서로 다른 Action 후보군을 생성
    """

    SYSTEM_PROMPT = """당신은 네트워크 엔지니어링 LLM 데이터 수집기입니다.
주어진 네트워크 요구사항에 대해 모델이 낼 수 있는 다양한 답변 후보군 4~5개를 생성하십시오.
후보군에는 최적의 정답(우선순위 4096 설정, root primary 등), 문법 오류(우선순위 5000 등 허용되지 않는 값),
그리고 CLI 명령어가 아닌 자연어 대화체로 답변해버린 포맷 오류(FORMAT_ERROR)가 포함되도록 다양성을 부여하십시오.

형식:
Candidate 1:
<think>VLAN 1의 우선순위를 4096으로 변경하여 루트 브리지 역할을 선점합니다.</think>
<commands>
spanning-tree vlan 1 priority 4096
</commands>

Candidate 2:
<think>Cisco 매크로 명령어를 사용하여 간결하게 루트로 지정합니다.</think>
<commands>
spanning-tree vlan 1 root primary
</commands>

Candidate 3:
<think>우선순위 값을 5000으로 잘못 입력하여 문법 오류가 발생합니다.</think>
<commands>
spanning-tree vlan 1 priority 5000
</commands>

Candidate 4:
<think>CLI 명령어 형식을 지키지 않고 자연어로만 답합니다.</think>
<commands>
SW1을 루트 브리지로 변경했습니다.
</commands>
"""

    def __init__(self, api_key: str = None, base_url: str = None, model: str = "gpt-4o"):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY", "")
        self.base_url = base_url or os.getenv("OPENAI_BASE_URL", None)
        self.model = model
        self.client = None
        if OpenAI and self.api_key:
            self.client = OpenAI(api_key=self.api_key, base_url=self.base_url)

    def generate_candidates(self, scenario: Scenario, count: int = 4) -> List[CandidateAction]:
        """후보군 생성. API Key 부재 시 사용자 정의 시나리오에 맞는 정밀 Mock 생성"""
        if not self.client:
            return self._mock_generate(scenario, count)

        user_content = f"""Scenario: {scenario.scenario_id}
Prompt: {scenario.task_description} (현재 상태: {scenario.current_state})
Target Device: {scenario.target_node}
Target VLAN: {scenario.vlan_id}
Expected Root: {scenario.expected_root_node}

총 {count}개의 다양한 응답 후보군을 생성해주세요.
"""
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": self.SYSTEM_PROMPT},
                    {"role": "user", "content": user_content}
                ],
                temperature=0.8,
            )
            raw_text = response.choices[0].message.content
            return self._parse_candidates(raw_text, count)
        except Exception as e:
            print(f"[Generator] LLM Call failed ({e}). Using mock candidates.")
            return self._mock_generate(scenario, count)

    def _parse_candidates(self, text: str, count: int) -> List[CandidateAction]:
        candidates = []
        pattern = r"Candidate\s*(\d+):?(.*?)(?=(Candidate\s*\d+:|$))"
        matches = list(re.finditer(pattern, text, re.DOTALL | re.IGNORECASE))

        for idx, match in enumerate(matches[:count], start=1):
            block = match.group(2).strip()
            
            think_match = re.search(r"<think>(.*?)</think>", block, re.DOTALL)
            thinking = think_match.group(1).strip() if think_match else ""

            cmd_match = re.search(r"<commands>(.*?)</commands>", block, re.DOTALL)
            if cmd_match:
                cmd_text = cmd_match.group(1).strip()
            else:
                code_match = re.search(r"```(?:cisco|bash)?(.*?)```", block, re.DOTALL)
                cmd_text = code_match.group(1).strip() if code_match else block

            # 한국어 설명문이거나 명령어가 아닌 경우 FORMAT_ERROR 플래그 설정
            lines = [line.strip() for line in cmd_text.splitlines() if line.strip()]
            is_format_error = False
            if lines and not any(l.startswith(("spanning-tree", "interface", "vlan", "no ", "default ")) for l in lines):
                is_format_error = True

            candidates.append(CandidateAction(
                candidate_id=idx,
                thinking=thinking,
                commands=lines,
                raw_response=cmd_text,
                is_format_error=is_format_error
            ))

        return candidates

    def _mock_generate(self, scenario: Scenario, count: int) -> List[CandidateAction]:
        """사용자가 제시한 시나리오 및 인터페이스에 맞춘 현실적인 GRPO 평가 후보군 생성"""
        vlan = scenario.vlan_id
        base_cmds = scenario.baseline_commands if scenario.baseline_commands else [f"spanning-tree vlan {vlan} priority 4096"]

        # 1. 정답 후보 (Baseline 정확한 명령어)
        cand1_cmds = list(base_cmds)
        cand1_resp = "\n".join(cand1_cmds)
        cand1_think = f"{scenario.task_description} 요구사항에 맞게 최적의 설정을 적용합니다."

        # 2. 대안 / 축약형 또는 다른 방식의 유효 후보
        from src.interface_normalizer import normalize_interface_name
        cand2_cmds = []
        for cmd in base_cmds:
            if "interface " in cmd:
                # 인터페이스 축약형 (예: interface Ethernet0/0 -> interface Et0/0)
                parts = cmd.split(maxsplit=1)
                short_if = normalize_interface_name(parts[1], short=True)
                cand2_cmds.append(f"interface {short_if}")
            elif "priority 4096" in cmd:
                cand2_cmds.append(f"spanning-tree vlan {vlan} root primary")
            else:
                cand2_cmds.append(cmd)
        if cand2_cmds == cand1_cmds:
            # 루트 변경 시 대안 매크로
            cand2_cmds = [f"spanning-tree vlan {vlan} root primary"] if not any("interface" in c for c in cand1_cmds) else cand1_cmds

        cand2_resp = "\n".join(cand2_cmds)
        cand2_think = f"대안 또는 축약형 명령어를 적용하여 구성을 완료합니다."

        # 3. 문법 오류 후보 (허용 범위를 벗어난 파라미터 등)
        cand3_cmds = []
        for cmd in base_cmds:
            if "priority" in cmd:
                cand3_cmds.append(re.sub(r"priority\s+\d+", "priority 5000", cmd))
            elif "cost" in cmd:
                cand3_cmds.append(re.sub(r"cost\s+\d+", "cost 999999999", cmd))
            else:
                cand3_cmds.append(cmd + " invalid_param")
        if not cand3_cmds:
            cand3_cmds = [f"spanning-tree vlan {vlan} priority 5000"]
        cand3_resp = "\n".join(cand3_cmds)
        cand3_think = f"파라미터 규격을 지키지 않아 CLI 구문 분석 에러가 발생합니다."

        # 4. 포맷 오류 후보 (CLI 대신 자연어)
        cand4_cmds = []
        cand4_resp = f"{scenario.target_node} 장비에 {scenario.task_description} 구성을 완료했습니다."
        cand4_think = f"CLI 명령어 블록 대신 설명 텍스트만 출력합니다 (형식 오류)."

        mock_list = [
            CandidateAction(
                candidate_id=1,
                thinking=cand1_think,
                commands=cand1_cmds,
                raw_response=cand1_resp,
                is_format_error=False
            ),
            CandidateAction(
                candidate_id=2,
                thinking=cand2_think,
                commands=cand2_cmds,
                raw_response=cand2_resp,
                is_format_error=False
            ),
            CandidateAction(
                candidate_id=3,
                thinking=cand3_think,
                commands=cand3_cmds,
                raw_response=cand3_resp,
                is_format_error=False
            ),
            CandidateAction(
                candidate_id=4,
                thinking=cand4_think,
                commands=cand4_cmds,
                raw_response=cand4_resp,
                is_format_error=True
            ),
        ]
        return mock_list[:count]
