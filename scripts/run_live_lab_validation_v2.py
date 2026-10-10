import asyncio
import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Tuple
from scrapli import AsyncScrapli
from rich.console import Console
from rich.table import Table

from src.config import Scenario
from src.interface_normalizer import apply_interface_mapping_to_commands

console = Console(highlight=False)

INIT_CONFIG_CMDS = [
    "username admin privilege 15 secret admin",
    "aaa new-model",
    "aaa authentication login default local",
    "aaa authorization exec default local",
    "spanning-tree mode rapid-pvst",
    "spanning-tree extend system-id",
    "vlan 10,20,30,40,100",
    "interface Ethernet0/1", "no shutdown",
    "interface Ethernet0/2", "no shutdown",
    "interface Ethernet0/3", "no shutdown",
    "interface Ethernet1/0", "no shutdown",
    "interface Ethernet1/1", "no shutdown",
    "line vty 0 4", "login local", "transport input ssh"
]

ERROR_PATTERNS = [
    r"% Invalid input detected",
    r"% Incomplete command",
    r"% Ambiguous command",
    r"% Command rejected",
    r"% Parameter value .*? is not valid",
    r"% In increments of",
    r"% Value out of range",
    r"% Bad [a-zA-Z0-9_-]+",
    r"% Configuration failed",
    r"% Unknown command"
]

INTERFACE_MAP = {
    "Gi0/1": "Ethernet0/1",
    "Gi0/2": "Ethernet0/2",
    "Gi0/3": "Ethernet0/3",
    "Gi0/4": "Ethernet1/0",
    "GigabitEthernet0/1": "Ethernet0/1",
    "GigabitEthernet0/2": "Ethernet0/2",
    "GigabitEthernet0/3": "Ethernet0/3",
    "GigabitEthernet0/4": "Ethernet1/0"
}

def adapt_commands_for_iol(commands: List[str]) -> List[str]:
    """IOL 스위치 환경에 맞게 인터페이스 매핑 및 IOS 표준 문법 적용"""
    mapped = apply_interface_mapping_to_commands(commands, INTERFACE_MAP)
    adapted = []
    for cmd in mapped:
        c = cmd
        # 1. GigabitEthernet 치환
        c = re.sub(r"\bGigabitEthernet0/1\b", "Ethernet0/1", c, flags=re.I)
        c = re.sub(r"\bGigabitEthernet0/2\b", "Ethernet0/2", c, flags=re.I)
        c = re.sub(r"\bGigabitEthernet0/3\b", "Ethernet0/3", c, flags=re.I)
        c = re.sub(r"\bGigabitEthernet0/4\b", "Ethernet1/0", c, flags=re.I)
        # 2. IOL L2-17.17 표준 Portfast 문법
        c = re.sub(r"spanning-tree portfast edge\b", "spanning-tree portfast", c, flags=re.I)
        c = re.sub(r"spanning-tree portfast normal\b", "no spanning-tree portfast", c, flags=re.I)
        c = re.sub(r"spanning-tree portfast network default\b", "spanning-tree portfast default", c, flags=re.I)
        c = re.sub(r"no spanning-tree portfast network default\b", "no spanning-tree portfast default", c, flags=re.I)
        c = re.sub(r"spanning-tree portfast edge default\b", "spanning-tree portfast default", c, flags=re.I)
        c = re.sub(r"no spanning-tree portfast edge default\b", "no spanning-tree portfast default", c, flags=re.I)
        adapted.append(c)
    return adapted

def check_cli_error(output: str) -> Tuple[bool, str]:
    for pat in ERROR_PATTERNS:
        m = re.search(pat, output, re.IGNORECASE)
        if m:
            return True, m.group(0)
    return False, ""

async def atomic_rollback(conn) -> bool:
    try:
        res = await conn.send_command("configure replace nvram:startup-config force")
        return "% Rollback failed" not in res.result
    except Exception:
        return False

async def test_single_scenario(conn, sc: dict) -> dict:
    sc_id = sc["scenario_id"]
    raw_cmds = sc.get("baseline_commands", [])
    adapted_cmds = adapt_commands_for_iol(raw_cmds)

    # 1. 사전 원자적 롤백 (이전 상태 100% 제거)
    await atomic_rollback(conn)

    # 특정 사전 조건이 필요한 시나리오 처리 (예: Po1 삭제 시 사전에 Po1 인터페이스 생성)
    if "no interface Port-channel" in " ".join(adapted_cmds):
        await conn.send_configs(["interface Port-channel 1"])

    # 2. 정답 baseline 명령어 주입
    config_res = await conn.send_configs(adapted_cmds)
    inj_output = config_res.result

    has_err, err_msg = check_cli_error(inj_output)

    # 3. 사후 원자적 롤백 (다음 테스트를 위한 완전한 초기화)
    await atomic_rollback(conn)

    status = "SYNTAX_ERROR" if has_err else "SUCCESS"
    return {
        "scenario_id": sc_id,
        "status": status,
        "error_msg": err_msg if has_err else None,
        "adapted_cmds": adapted_cmds,
        "inj_output": inj_output.strip()
    }

async def main():
    console.print("\n[bold green]====================================================================[/bold green]")
    console.print("[bold yellow]⚡ Cisco IOL 실장비 v2 정밀 검증 (인터페이스 매핑 & IOS 문법 정규화)[/bold yellow]")
    console.print("[bold green]====================================================================[/bold green]\n")

    lab_nodes_path = Path("configs/lab_nodes_all.json")
    with open(lab_nodes_path, "r", encoding="utf-8") as f:
        lab_nodes = json.load(f)

    test_node_cfg = lab_nodes["clab_node_1"]
    sc_path = Path("data/grpo_scenario_multitier_150.json")
    with open(sc_path, "r", encoding="utf-8") as f:
        scenarios = json.load(f)

    params = {
        "host": test_node_cfg["host"],
        "port": test_node_cfg["port"],
        "auth_username": test_node_cfg["auth_username"],
        "auth_password": test_node_cfg["auth_password"],
        "auth_strict_key": False,
        "platform": "cisco_iosxe",
        "transport": "asyncssh",
        "timeout_socket": 15,
        "timeout_transport": 15,
        "timeout_ops": 20,
    }

    results = []
    success_count = 0
    error_count = 0

    table = Table(title="Live Lab v2 Injection Results", header_style="bold cyan")
    table.add_column("No", justify="center", width=4)
    table.add_column("시나리오 ID", width=34)
    table.add_column("적용 명령어 (IOL 매핑)", width=36)
    table.add_column("상태", justify="center", width=12)
    table.add_column("실장비 피드백", ratio=2)

    async with AsyncScrapli(**params) as conn:
        for idx, sc in enumerate(scenarios, 1):
            res = await test_single_scenario(conn, sc)
            results.append(res)

            cmd_disp = " ; ".join(res["adapted_cmds"])[:34]
            if res["status"] == "SUCCESS":
                success_count += 1
                if idx in [1, 21, 29, 31, 89, 104, 150]:
                    table.add_row(str(idx), sc["scenario_id"], cmd_disp, "[bold green]SUCCESS[/bold green]", "IOL 실장비 주입 성공")
            else:
                error_count += 1
                table.add_row(str(idx), sc["scenario_id"], cmd_disp, "[bold red]SYNTAX_ERR[/bold red]", res["error_msg"] or "오류")

    console.print(table)
    console.print("\n" + "=" * 60)
    console.print(f"  [bold]Cisco IOL 실장비 v2 검증 최종 집계[/bold]")
    console.print(f"  - 총 테스트 시나리오: [cyan]{len(scenarios)}개[/cyan]")
    console.print(f"  - 성공 (SUCCESS): [bold green]{success_count}개[/bold green] ({success_count/len(scenarios)*100:.1f}%)")
    console.print(f"  - 구문 오류 (SYNTAX_ERROR): [bold red]{error_count}개[/bold red]")
    console.print("=" * 60)

    report_path = Path("docs/live_lab_validation_report_v2.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    console.print(f"[green]✔ v2 실장비 검증 리포트 저장 완료: {report_path}[/green]\n")

if __name__ == "__main__":
    asyncio.run(main())
