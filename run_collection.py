import argparse
import asyncio
import json
import sys
from pathlib import Path

from rich.console import Console
from rich.panel import Panel

from src.config import LabNode, Scenario, load_lab_nodes
from src.generator import ActionGenerator
from src.evaluator import SpanningTreeEvaluator
from src.pipeline import GRPODatasetPipeline

console = Console(highlight=False)


def build_default_lab_nodes(count: int = 8) -> dict:
    """기본 8개 가상 랩 노드 연결 프로파일 생성 (mgmt-ipv4: 192.168.100.x, port 22, admin/admin)"""
    labs = {}
    for i in range(1, count + 1):
        lab_id = f"clab_node_{i}"
        labs[lab_id] = LabNode(
            host=f"192.168.100.{i * 10 + 1}",
            port=22,
            auth_username="admin",
            auth_password="admin",
            platform="cisco_iosxe"
        )
    return labs


async def main():
    parser = argparse.ArgumentParser(description="GRPO Network Data Collection Pipeline (Live & Simulation)")
    parser.add_argument("--topology", type=str, choices=["unit", "multitier"], default="unit",
                        help="토폴로지 모드: unit (3대 랩 단위 테스트) 또는 multitier (6~8대 다계층 통합 랩)")
    parser.add_argument("--scenarios", type=str, default=None, help="시나리오 JSON 파일 경로 (미지정 시 topology 모드에 맞춰 자동 선택)")
    parser.add_argument("--output", type=str, default=None, help="저장할 JSONL 파일 경로 (미지정 시 topology 모드에 맞춰 자동 선택)")
    parser.add_argument("--labs-config", type=str, default=None, help="랩 접속정보 파일 경로 (미지정 시 topology 모드에 맞춰 자동 선택)")
    parser.add_argument("--lab-count", type=int, default=8, help="가상 랩 인스턴스 수 (기본: 8)")
    parser.add_argument("--candidate-count", type=int, default=8, help="시나리오당 생성할 후보 액션 수 (기본: 8)")
    parser.add_argument("--filter-quality", action="store_true", default=True, help="GRPO 학습 유효 신호(sigma > 0) 품질 게이트 필터링 활성화 (기본: True)")
    parser.add_argument("--startup-wait", type=int, default=30, help="Live 랩 부팅 및 SSH 준비 대기 시간(초) (기본: 30)")
    parser.add_argument("--init-config", type=str, default="configs/initial_config.cfg", help="최초 접속 시 자동 주입할 베이스라인 설정 파일 (기본: configs/initial_config.cfg)")
    parser.add_argument("--skip-init", action="store_true", default=False, help="최초 베이스라인 설정 주입 건너뛰기")
    parser.add_argument("--dry-run", action="store_true", default=False, help="모의 시뮬레이션 모드 (장비 연결 없이 동작)")
    parser.add_argument("--live", action="store_true", help="실제 Containerlab 인스턴스에 SSH 연결")
    args = parser.parse_args()

    # 토폴로지 모드에 따른 기본값 자동 분기
    if args.topology == "multitier":
        default_scenarios = "data/grpo_scenario_multitier_150.json"
        default_output = "data/grpo_dataset_multitier_150.jsonl"
        default_cfg = "configs/lab_nodes_integration.json"
    else:
        default_scenarios = "data/grpo_initial_scenario_120.json" if Path("data/grpo_initial_scenario_120.json").exists() else "data/grpo_initial_scenario_80.json"
        default_output = "data/grpo_dataset_120.jsonl"
        default_cfg = "configs/lab_nodes_8.json" if Path("configs/lab_nodes_8.json").exists() else "configs/lab_nodes.json"

    scenario_path_str = args.scenarios or default_scenarios
    output_path_str = args.output or default_output
    labs_cfg_str = args.labs_config or default_cfg

    # 실행 모드 판정: --live가 지정되지 않고 --dry-run도 명시되지 않았다면 안전을 위해 dry-run 우선
    dry_run = not args.live

    # 1. 시나리오 로드
    scenario_file = Path(scenario_path_str)
    if not scenario_file.exists():
        console.print(f"[bold red]오류: 시나리오 파일({scenario_path_str})을 찾을 수 없습니다.[/bold red]")
        return

    with open(scenario_file, "r", encoding="utf-8") as f:
        raw_scenarios = json.load(f)
    scenarios = [Scenario(**s) for s in raw_scenarios]

    # 2. 컴포넌트 초기화 및 랩 정보 로드
    labs_config_path = Path(labs_cfg_str)
    if labs_config_path.exists():
        console.print(f"[bold green][Config][/bold green] 랩 접속정보 파일 로드: [cyan]{labs_config_path.resolve()}[/cyan]")
        labs = load_lab_nodes(labs_config_path)
    else:
        console.print(f"[bold yellow][Config][/bold yellow] 설정 파일이 없어 기본값({args.lab_count}개)으로 생성합니다.")
        labs = build_default_lab_nodes(count=args.lab_count)

    generator = ActionGenerator()
    evaluator = SpanningTreeEvaluator(
        success_reward=200.0,
        syntax_error_reward=-150.0,
        format_error_reward=-200.0,
        ineffective_reward=0.0
    )

    pipeline = GRPODatasetPipeline(
        lab_nodes=labs,
        generator=generator,
        evaluator=evaluator,
        dry_run=dry_run
    )

    console.print(Panel(
        f"[bold white]실행 모드:[/bold white] {'[bold red]🔴 LIVE (실제 스위치 연결)[/bold red]' if not dry_run else '[bold green]🟢 DRY-RUN (소프트웨어 시뮬레이션)[/bold green]'}\n"
        f"[bold white]토폴로지 분류:[/bold white] {'[bold magenta]다계층 통합 랩 (Multi-tier Integration)[/bold magenta]' if args.topology == 'multitier' else '[bold cyan]단위 기능 랩 (Unit Test 3-node)[/bold cyan]'}\n"
        f"[bold white]시나리오 수:[/bold white] {len(scenarios)}개 | [bold white]병렬 랩 노드:[/bold white] {len(labs)}개 | [bold white]후보군(G):[/bold white] {args.candidate_count}개\n"
        f"[bold white]품질 게이트:[/bold white] {'[bold green]활성화 (σ > 0 샘플 엄선)[/bold green]' if args.filter_quality else '[dim]비활성화[/dim]'}\n"
        f"[bold white]접속 계정:[/bold white] admin / admin (mgmt-ipv4: 192.168.100.x, port: 22)\n"
        f"[bold white]초기 설정 파일:[/bold white] {args.init_config} (건너뛰기: {args.skip_init})\n"
        f"[bold white]출력 파일:[/bold white] {output_path_str}",
        title="[bold yellow]🚀 GRPO 네트워크 학습 데이터 수집 파이프라인[/bold yellow]",
        border_style="yellow"
    ))

    # 3. Live 모드 시 대기 (부팅 및 데몬 초기화)
    if not dry_run and args.startup_wait > 0:
        console.print(f"\n[bold yellow]⏳ 가상 스위치 부팅 및 SSH 접속 준비를 위해 {args.startup_wait}초간 대기합니다...[/bold yellow]")
        for sec in range(args.startup_wait, 0, -5):
            console.print(f"   남은 대기 시간: [bold cyan]{sec}초[/bold cyan]...")
            await asyncio.sleep(min(5, sec))
        console.print("[bold green]✔ 대기 완료![/bold green]\n")

    # 4. 최초 접속과 동시에 베이스라인 설정 자동 주입
    if not args.skip_init:
        all_nodes_path = Path("configs/lab_nodes_24.json")
        bootstrap_targets = load_lab_nodes(all_nodes_path) if all_nodes_path.exists() else labs
        await pipeline.bootstrap_labs(args.init_config, target_nodes=bootstrap_targets)

    # 5. 파이프라인 시나리오 주입 실행 (품질 게이트 적용)
    results = await pipeline.run_pipeline(
        scenarios=scenarios,
        output_jsonl_path=output_path_str,
        candidate_count=args.candidate_count,
        filter_quality=args.filter_quality
    )


if __name__ == "__main__":
    asyncio.run(main())
