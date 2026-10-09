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

    SYSTEM_PROMPT = """당신은 고성능 네트워크 엔지니어링 LLM 데이터 수집기입니다.
주어진 네트워크 요구사항에 대해 3B 모델이 L2/STP 정책을 최적화할 수 있도록,
반드시 <think> 태그 내에 [1. 토폴로지/상태 분석 -> 2. 파라미터 및 타이브레이커 계산 -> 3. 영향도(Blast Radius) 검토 -> 4. 명령어 도출] 4단계 CoT 추론 과정을 포함하여 4개의 다양한 후보군을 생성하십시오.

후보군 다양성 구성:
- Candidate 1 (최적 정답): 표준 권장 Cisco IOS 명령어와 논리적 근거
- Candidate 2 (대안/축약형): 인터페이스 축약 또는 매크로를 활용한 또 다른 유효 설정
- Candidate 3 (문법 오류): 파라미터 범위 초과 또는 오타로 인한 CLI 구문 오류 (-150점 유도)
- Candidate 4 (포맷 오류): CLI 명령어 태그 없이 자연어로만 응답한 형식 오류 (-200점 유도)

형식:
Candidate 1:
<think>
1. 현재 상태 분석: 현재 VLAN 1의 루트 브리지는 SW3(Priority 32768)이며, SW1은 Non-root 상태임.
2. 파라미터 계산: SW1을 확실한 루트로 선출하기 위해 표준 4096 스텝 단위인 Priority 4096을 적용해야 함.
3. 영향도 검토: 우선순위 하향 조정 시 즉시 BPDU를 발송하여 타이브레이커 1단계(Root BID)를 만족하며, 일시적 TCN 발생 후 1~3초 내 수렴.
4. 명령어 도출: 'spanning-tree vlan 1 priority 4096' 명령어를 구성 모드에서 실행.
</think>
<commands>
spanning-tree vlan 1 priority 4096
</commands>

Candidate 2:
<think>
1. 현재 상태 분석: 루트 선출을 위해 Cisco 매크로 설정 검토.
2. 파라미터 계산: 'root primary' 매크로는 현재 루트보다 최소 2단계(8192) 낮은 값을 자동 할당함.
3. 영향도 검토: 표준 수치 지정과 동일하게 안전한 루트 선출 보장.
4. 명령어 도출: 간결한 매크로 명령어 'spanning-tree vlan 1 root primary' 적용.
</think>
<commands>
spanning-tree vlan 1 root primary
</commands>

Candidate 3:
<think>
1. 오류 분석: 우선순위 값을 표준 4096의 배수가 아닌 임의의 값(5000)으로 잘못 지정함.
2. 영향도 검토: CLI 파서에서 '% Invalid input' 구문 에러를 반환하여 설정이 적용되지 않음.
</think>
<commands>
spanning-tree vlan 1 priority 5000
</commands>

Candidate 4:
<think>
형식 에러 발생: <commands> 태그 내에 실행 가능한 CLI 명령어 대신 일반 대화체 텍스트만 생성함.
</think>
<commands>
SW1 장비의 VLAN 1 루트 우선순위 구성을 완료했습니다.
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
        cand1_think = (
            f"1. 토폴로지 분석: 대상 노드 {scenario.target_node}, 대상 VLAN {scenario.vlan_id}, 현재 상태는 '{scenario.current_state}'임.\n"
            f"2. 파라미터 및 타이브레이커 계산: 요구사항 '{scenario.task_description}'에 부합하도록 표준 파라미터 적용.\n"
            f"3. 영향도(Blast Radius) 검토: 설정 적용 후 안정적 수렴 보장.\n"
            f"4. 명령어 도출: {', '.join(cand1_cmds)}를 순차 실행."
        )

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
        cand2_think = (
            f"1. 토폴로지 분석: 대상 장비 {scenario.target_node}의 대체 구성을 검토함.\n"
            f"2. 파라미터 계산: 인터페이스 축약형 또는 Cisco 기본 매크로 문법을 활용하여 동일한 L2 제어 목표 달성.\n"
            f"3. 영향도 검토: 축약 문법 역시 표준 구문과 동등하게 파싱되어 정상 수렴됨.\n"
            f"4. 명령어 도출: {', '.join(cand2_cmds)} 적용."
        )

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
        cand3_think = (
            f"1. 문법 검토: 설정 대상 파라미터 값에 유효하지 않은 규격 외 수치({cand3_cmds[-1]})를 지정함.\n"
            f"2. 영향도 검토: Cisco IOS CLI 파서에서 '% Invalid input detected' 구문 에러를 반환하여 설정이 기각됨."
        )

        # 4. 포맷 오류 후보 (CLI 대신 자연어)
        cand4_cmds = []
        cand4_resp = f"{scenario.target_node} 장비에 {scenario.task_description} 구성을 완료했습니다."
        cand4_think = (
            f"형식 검토: 모델이 실행 가능한 CLI 명령어 블록 대신 일반 자연어 문장만 출력함 (포맷 실패)."
        )

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
