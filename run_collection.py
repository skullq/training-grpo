import argparse
import asyncio
import json
from pathlib import Path

from src.config import LabNode, Scenario
from src.generator import ActionGenerator
from src.evaluator import SpanningTreeEvaluator
from src.pipeline import GRPODatasetPipeline


def build_default_lab_nodes(count: int = 5) -> dict:
    """4~8개 가상 랩 노드 연결 프로파일 생성 (Containerlab 포트 매핑)"""
    labs = {}
    base_port = 2201
    for i in range(1, count + 1):
        lab_id = f"clab_node_{i}"
        labs[lab_id] = LabNode(
            host="127.0.0.1",
            port=base_port + (i - 1),
            auth_username="admin",
            auth_password="admin",
            platform="cisco_iosxe"
        )
    return labs


async def main():
    parser = argparse.ArgumentParser(description="GRPO Network Data Collection Pipeline")
    parser.add_argument("--scenarios", type=str, default="data/sample_scenarios.json", help="Path to scenarios JSON file")
    parser.add_argument("--output", type=str, default="data/grpo_dataset.jsonl", help="Path to output JSONL file")
    parser.add_argument("--lab-count", type=int, default=5, help="Number of virtual labs (default: 5)")
    parser.add_argument("--candidate-count", type=int, default=5, help="Number of candidate actions per scenario (default: 5)")
    parser.add_argument("--dry-run", action="store_true", default=True, help="Run simulation mode without live Containerlab")
    parser.add_argument("--live", action="store_true", help="Connect to actual Containerlab instances")
    args = parser.parse_args()

    dry_run = not args.live if args.live else args.dry_run

    # 1. 시나리오 로드
    scenario_file = Path(args.scenarios)
    if not scenario_file.exists():
        print(f"Error: {args.scenarios} not found.")
        return

    with open(scenario_file, "r", encoding="utf-8") as f:
        raw_scenarios = json.load(f)
    scenarios = [Scenario(**s) for s in raw_scenarios]

    # 2. 컴포넌트 초기화
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

    print(f"=== Starting GRPO Data Collection (Dry Run: {dry_run}) ===")
    print(f"Total Scenarios: {len(scenarios)} | Parallel Labs: {args.lab_count} | Candidates/Prompt: {args.candidate_count}")
    
    results = await pipeline.run_pipeline(
        scenarios=scenarios,
        output_jsonl_path=args.output,
        candidate_count=args.candidate_count
    )

    print(f"\n[Done] Successfully processed {len(results)} scenarios. Check {args.output}")


if __name__ == "__main__":
    asyncio.run(main())
