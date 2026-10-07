import json
import argparse
import sys
from pathlib import Path

# Windows 터미널 cp949 인코딩 대응
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from rich.console import Console
from rich.table import Table
from rich.panel import Panel

console = Console(highlight=False)

def display_dataset(file_path: str = "data/grpo_dataset.jsonl", limit: int = 5, scenario_id: str = None):
    path = Path(file_path)
    if not path.exists():
        console.print(f"[red]파일을 찾을 수 없습니다: {file_path}[/red]")
        return

    records = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                records.append(json.loads(line))

    console.print(Panel(
        f"[bold green][GRPO Dataset Viewer][/bold green]\n"
        f"파일: [cyan]{path.resolve()}[/cyan] | 총 시나리오: [yellow]{len(records)}개[/yellow]",
        border_style="green"
    ))

    displayed = 0
    for rec in records:
        sid = rec.get("scenario_id", "")
        prompt = rec.get("prompt", "")
        group_outputs = rec.get("group_outputs", [])

        if scenario_id and scenario_id not in sid:
            continue

        table = Table(
            title=f"[{sid}] {prompt}",
            title_justify="left",
            header_style="bold magenta",
            show_lines=True,
            expand=True
        )
        table.add_column("No", justify="center", width=4)
        table.add_column("생성된 Action (CLI / 응답)", style="cyan", ratio=5)
        table.add_column("상태 (Status)", justify="center", width=14)
        table.add_column("Raw Reward", justify="right", width=12)
        table.add_column("Advantage", justify="right", width=12)

        for idx, item in enumerate(group_outputs, 1):
            status = item.get("status", "")
            if status == "SUCCESS":
                status_styled = "[bold green]SUCCESS[/bold green]"
            elif status == "SYNTAX_ERROR":
                status_styled = "[bold red]SYNTAX_ERROR[/bold red]"
            elif status == "FORMAT_ERROR":
                status_styled = "[bold magenta]FORMAT_ERROR[/bold magenta]"
            else:
                status_styled = "[yellow]INEFFECTIVE[/yellow]"

            reward = item.get("raw_reward", 0.0)
            reward_styled = f"[green]+{reward:.1f}[/green]" if reward > 0 else (f"[red]{reward:.1f}[/red]" if reward < 0 else "0.0")
            adv = item.get("relative_advantage", 0.0)
            adv_styled = f"[bold green]+{adv:.2f}[/bold green]" if adv > 0 else (f"[bold red]{adv:.2f}[/bold red]" if adv < 0 else "0.00")

            table.add_row(
                str(idx),
                item.get("output", "").strip(),
                status_styled,
                reward_styled,
                adv_styled
            )

        console.print(table)
        console.print()
        displayed += 1
        if limit and displayed >= limit and not scenario_id:
            break

    if not scenario_id and limit and len(records) > limit:
        console.print(f"[dim]... 외 {len(records) - limit}개 시나리오 생략됨. (전체 보기는 --limit 0 또는 --scenario ID)[/dim]\n")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="GRPO Dataset Pretty Viewer")
    parser.add_argument("--file", default="data/grpo_dataset.jsonl", help="JSONL 파일 경로")
    parser.add_argument("--limit", type=int, default=5, help="출력할 시나리오 수 (0=전체)")
    parser.add_argument("--scenario", type=str, default=None, help="특정 시나리오 ID 필터")
    args = parser.parse_args()
    display_dataset(args.file, limit=args.limit, scenario_id=args.scenario)
