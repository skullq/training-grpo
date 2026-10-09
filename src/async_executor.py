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

                # 2. 동적 프로토콜 수렴(Dynamic Convergence Polling)
                # 초기 최소 안정화 대기 (1.5초 또는 wait_seconds 중 작은 값)
                initial_wait = min(1.5, wait_seconds)
                await asyncio.sleep(initial_wait)
                remaining_wait = max(0.0, wait_seconds - initial_wait)

                # 상태 검증 명령어 첫 실행
                verify_response = await conn.send_command(verify_cmd)
                verification_output = verify_response.result

                # 3. 과도기 상태(Listening / Learning / LIS / LRN) 감지 시 동적 폴링
                transitional_keywords = ["lis", "lrn", "listening", "learning"]
                poll_interval = 1.0
                elapsed = 0.0

                def is_transitional(output_str: str) -> bool:
                    lines = output_str.lower().splitlines()
                    for line in lines:
                        if any(kw in line for kw in transitional_keywords):
                            return True
                    return False

                # 과도기 상태가 사라지고 완전 수렴(FWD/BLK 등)될 때까지 최대 대기시간 내에서 1초 주기 폴링
                while remaining_wait > 0 and elapsed < remaining_wait:
                    if not is_transitional(verification_output):
                        # 이미 안정 상태로 수렴 완료 -> 조기 탈출 (Early Exit)
                        break
                    await asyncio.sleep(poll_interval)
                    elapsed += poll_interval
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

        # 오류 명령어 시뮬레이션
        if "invalid" in cmd_text or "error" in cmd_text or "priority 5000" in cmd_text or "999999999" in cmd_text:
            return "% Invalid input detected at '^' marker.", ""

        from src.interface_normalizer import normalize_interface_name, INTERFACE_REGEX
        import re

        # 명령어로부터 인터페이스 및 파라미터 추출
        iface_match = INTERFACE_REGEX.search(" ".join(commands))
        active_iface_short = normalize_interface_name(iface_match.group(0), short=True) if iface_match else "Et0/0"
        
        # 기본 포트 상태
        cost_val = "19"
        prio_val = "128"

        cost_match = re.search(r"cost\s+(\d+)", cmd_text)
        if cost_match:
            cost_val = cost_match.group(1)

        prio_match = re.search(r"port-priority\s+(\d+)", cmd_text)
        if prio_match:
            prio_val = prio_match.group(1)

        is_root_set = ("spanning-tree vlan" in cmd_text and ("root primary" in cmd_text or "priority 0" in cmd_text or "priority 4096" in cmd_text))
        
        root_str = "This bridge is the root" if is_root_set else "Address     5000.0002.0000"
        bridge_prio = "4096" if is_root_set else "32768"

        # 검증 명령어 유형에 따른 맞춤형 모의 show 출력 생성
        verify_cmd_lower = verify_cmd.lower()

        if "trunk" in verify_cmd_lower:
            mock_show = f"""
Port        Mode             Encapsulation  Status        Native vlan
{active_iface_short:<11} on               802.1q         trunking      1

Port        Vlans allowed on trunk
{active_iface_short:<11} 1-4094

Port        Vlans allowed and active in management domain
{active_iface_short:<11} 10,20,30,40,100

Port        Vlans in spanning tree forwarding state and not pruned
{active_iface_short:<11} 10,20,30,40,100
"""
        elif "detail" in verify_cmd_lower:
            is_edge = "edge" in cmd_text or "portfast" in cmd_text
            is_net = "network" in cmd_text
            edge_str = "Portfast edge is enabled" if is_edge else "Portfast edge is disabled"
            net_str = "Network port (Bridge Assurance) is enabled" if is_net else "Network port is disabled"
            p2p_str = "Link type is point-to-point" if "point-to-point" in cmd_text else "Link type is point-to-point by default"

            mock_show = f"""
 Port 2 ({active_iface_short}) of VLAN0001 is designated forwarding 
   Port path cost {cost_val}, Port priority {prio_val}, Port Identifier {prio_val}.2.
   Designated root has priority 32768, address 5000.0001.0000
   Designated bridge has priority 32768, address 5000.0001.0000
   {p2p_str}
   {edge_str}
   {net_str}
   BPDU: sent 120, received 115
"""
        elif "etherchannel" in verify_cmd_lower:
            mock_show = f"""
Group  Port-channel  Protocol    Ports
------+-------------+-----------+-----------------------------------------------
1      Po1(SU)          LACP     Et0/1(P)    Et0/2(P)    
"""
        elif "mst" in verify_cmd_lower:
            mock_show = f"""
Name      [REGION1]
Revision  1     Instances configured 2

Instance  Vlans mapped
--------  ---------------------------------------------------------------------
0         1-9,11-19,21-4094
1         10,20
-------------------------------------------------------------------------------
"""
        elif "errdisable" in verify_cmd_lower:
            mock_show = f"""
ErrDisable Reason            Status
-----------------            ------
bpduguard                    Enabled
"""
        else:
            mock_show = f"""
VLAN0001
  Spanning tree enabled protocol rstp
  Root ID    Priority    {bridge_prio}
             {root_str}
             Hello Time   2 sec  Max Age 20 sec  Forward Delay 15 sec

  Bridge ID  Priority    {bridge_prio}
             Address     5000.0001.0000
             Hello Time   2 sec  Max Age 20 sec  Forward Delay 15 sec
             Aging Time  300 sec

Interface           Role Sts Cost      Prio.Nbr Type
------------------- ---- --- --------- -------- --------------------------------
{active_iface_short:<19} Desg FWD {cost_val:<9} {prio_val}.1    P2p
Et0/1               Altn BLK 19        128.2    P2p
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

    async def bootstrap_initial_configs(
        self,
        initial_commands: List[str],
        target_nodes: Dict[str, LabNode] = None
    ) -> Dict[str, Tuple[bool, str]]:
        """
        랩 시작 시 최초 접속과 동시에 모든 가상 스위치에 베이스라인 초기 설정을 일괄 병렬 주입
        """
        nodes = target_nodes if target_nodes is not None else self.lab_configs
        if self.dry_run or AsyncScrapli is None:
            return {lab_id: (True, "Mock initial config applied") for lab_id in nodes}

        tasks = []
        for lab_id, node_cfg in nodes.items():
            tasks.append(self._apply_init_config(lab_id, node_cfg, initial_commands))

        outcomes = await asyncio.gather(*tasks)
        results = {}
        for lab_id, success, msg in outcomes:
            results[lab_id] = (success, msg)
        return results

    async def _apply_init_config(self, lab_id: str, node_cfg: LabNode, initial_commands: List[str]) -> Tuple[str, bool, str]:
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
        try:
            async with AsyncScrapli(**device_params) as conn:
                await conn.send_configs(initial_commands)
                await conn.send_command("write memory")
                return (lab_id, True, f"{node_cfg.host}:{node_cfg.port} 초기 설정 및 저장 완료")
        except Exception as e:
            logger.error(f"[{lab_id}] Bootstrap config error: {e}")
            return (lab_id, False, str(e))

