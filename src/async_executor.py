import asyncio
from typing import List, Dict, Tuple
import logging

try:
    from scrapli import AsyncScrapli
except ImportError:
    AsyncScrapli = None

from src.config import LabNode

logger = logging.getLogger("AsyncLabExecutor")


class AsyncLabExecutor:
    """
    Asyncio + Scrapli를 활용하여 4~8개의 독립 가상 랩(Containerlab)에
    비동기로 명령어를 주입하고 결과를 병렬 수집하는 실행기
    """

    def __init__(self, lab_configs: Dict[str, LabNode], dry_run: bool = False):
        """
        :param lab_configs: {"lab_1": LabNode(...), "lab_2": LabNode(...), ...}
        :param dry_run: 실제 장비가 없을 때 모의 시뮬레이션 모드 활성화
        """
        self.lab_configs = lab_configs
        self.dry_run = dry_run

    async def _execute_single_lab(
        self,
        lab_id: str,
        node_cfg: LabNode,
        commands: List[str],
        verify_cmd: str,
        wait_seconds: float = 3.0
    ) -> Tuple[str, str]:
        """
        단일 랩에 비동기 접속 -> 설정 주입 -> 대기(수렴) -> 검증 명령어 실행 -> 세션 종료
        """
        if self.dry_run or AsyncScrapli is None:
            return await self._mock_execution(lab_id, commands, verify_cmd, wait_seconds)

        device_params = {
            "host": node_cfg.host,
            "port": node_cfg.port,
            "auth_username": node_cfg.auth_username,
            "auth_password": node_cfg.auth_password,
            "auth_strict_key": node_cfg.auth_strict_key,
            "platform": node_cfg.platform,
            "transport": "asyncssh",
            "timeout_socket": 10,
            "timeout_transport": 10,
            "timeout_ops": 15,
        }

        injection_output = ""
        verification_output = ""

        try:
            async with AsyncScrapli(**device_params) as conn:
                # 1. 설정 모드 진입 및 명령어 주입
                config_response = await conn.send_configs(commands)
                injection_output = config_response.result

                # 2. 프로토콜 수렴(Convergence) 대기
                # Rapid-PVST / RSTP의 경우 1~3초 내 수렴
                await asyncio.sleep(wait_seconds)

                # 3. 상태 검증 명령어 실행 (show spanning-tree 등)
                verify_response = await conn.send_command(verify_cmd)
                verification_output = verify_response.result

        except Exception as e:
            logger.error(f"[{lab_id}] Connection or execution error: {e}")
            injection_output = f"% Error: Connection failed - {str(e)}"
            verification_output = ""

        return injection_output, verification_output

    async def _mock_execution(
        self, lab_id: str, commands: List[str], verify_cmd: str, wait_seconds: float
    ) -> Tuple[str, str]:
        """시뮬레이션 환경용 모의 응답 생성기"""
        await asyncio.sleep(0.1)  # 비동기 지연 시뮬레이션
        cmd_text = " ".join(commands).lower()

        # 오류 명령어 시뮬레이션 (명시적 오류 키워드 또는 4096 배수가 아닌 비정상 priority 값)
        if "invalid" in cmd_text or "error" in cmd_text or "priority 5000" in cmd_text:
            return "% Invalid input detected at '^' marker.", ""

        # 루트 브리지 설정 명령어 포함 여부 확인
        if "spanning-tree vlan" in cmd_text and ("root primary" in cmd_text or "priority 0" in cmd_text or "priority 4096" in cmd_text):
            mock_show = f"""
VLAN0001
  Spanning tree enabled protocol rstp
  Root ID    Priority    4096
             Address     5000.0001.0000
             This bridge is the root
             Hello Time   2 sec  Max Age 20 sec  Forward Delay 15 sec

  Bridge ID  Priority    4096
             Address     5000.0001.0000
             Hello Time   2 sec  Max Age 20 sec  Forward Delay 15 sec
             Aging Time  300 sec

Interface           Role Sts Cost      Prio.Nbr Type
------------------- ---- --- --------- -------- --------------------------------
Gi0/1               Desg FWD 4         128.1    P2p
Gi0/2               Desg FWD 4         128.2    P2p
"""
            return "Configuration applied successfully.", mock_show
        else:
            # 다른 브리지가 루트인 경우
            mock_show = """
VLAN0001
  Spanning tree enabled protocol rstp
  Root ID    Priority    32768
             Address     5000.0002.0000
             Cost        4
             Port        1 (GigabitEthernet0/1)

  Bridge ID  Priority    32768
             Address     5000.0001.0000
Interface           Role Sts Cost      Prio.Nbr Type
------------------- ---- --- --------- -------- --------------------------------
Gi0/1               Root FWD 4         128.1    P2p
Gi0/2               Altn BLK 4         128.2    P2p
"""
            return "Configuration applied successfully.", mock_show

    async def run_parallel_injections(
        self,
        candidate_commands: List[Tuple[int, List[str]]],
        verify_cmd: str,
        wait_seconds: float = 3.0
    ) -> List[Tuple[int, str, str, str]]:
        """
        N개의 Action 후보군을 N개의 가상 랩에 동시에 비동기로 주입
        
        :param candidate_commands: [(candidate_id, [commands]), ...]
        :return: [(candidate_id, lab_id, injection_output, verify_output), ...]
        """
        lab_ids = list(self.lab_configs.keys())
        tasks = []

        for idx, (cand_id, cmds) in enumerate(candidate_commands):
            lab_id = lab_ids[idx % len(lab_ids)]
            node_cfg = self.lab_configs[lab_id]
            tasks.append(
                self._wrap_task(cand_id, lab_id, node_cfg, cmds, verify_cmd, wait_seconds)
            )

        results = await asyncio.gather(*tasks)
        return results

    async def _wrap_task(
        self, cand_id: int, lab_id: str, node_cfg: LabNode, cmds: List[str], verify_cmd: str, wait_sec: float
    ) -> Tuple[int, str, str, str]:
        inj_out, verify_out = await self._execute_single_lab(lab_id, node_cfg, cmds, verify_cmd, wait_sec)
        return (cand_id, lab_id, inj_out, verify_out)
