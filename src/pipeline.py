import asyncio
import json
import logging
from typing import List, Dict
from pathlib import Path

from src.config import LabNode, Scenario, GRPOScenarioRecord, GroupOutputItem
from src.generator import ActionGenerator
from src.async_executor import AsyncLabExecutor
from src.evaluator import SpanningTreeEvaluator
from src.advantage import calculate_grpo_advantages

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("GRPO-Pipeline")


class GRPODatasetPipeline:
    """
    네트워크 가상 랩 환경과 LLM 생성기를 결합한 GRPO 데이터 수집 및 Advantage 가공 파이프라인
    """

    def __init__(
        self,
        lab_nodes: Dict[str, LabNode],
        generator: ActionGenerator,
        evaluator: SpanningTreeEvaluator,
        dry_run: bool = True
    ):
        self.lab_nodes = lab_nodes
        self.generator = generator
        self.evaluator = evaluator
        self.executor = AsyncLabExecutor(lab_nodes, dry_run=dry_run)

    async def process_scenario(self, scenario: Scenario, candidate_count: int = 4) -> GRPOScenarioRecord:
        """단일 시나리오 처리 (생성 -> 랩 병렬 주입 -> 채점 -> Relative Advantage 계산)"""
        logger.info(f"Processing Scenario: {scenario.scenario_id} - {scenario.task_description}")

        # 1. Action 후보군 생성 (G=4~5)
        candidates = self.generator.generate_candidates(scenario, count=candidate_count)
        logger.info(f"Generated {len(candidates)} candidates for {scenario.scenario_id}")

        # 2. 병렬 랩 주입 준비 (포맷 오류가 아닌 실제 명령어 보유 후보만 주입)
        valid_commands_for_injection = [
            (c.candidate_id, c.commands) for c in candidates if c.commands and not c.is_format_error
        ]
        verify_cmd = f"show spanning-tree vlan {scenario.vlan_id}"

        # 3. 비동기 동시 주입 및 결과 수집 (3초 수렴 대기)
        lab_results_map = {}
        if valid_commands_for_injection:
            raw_results = await self.executor.run_parallel_injections(
                valid_commands_for_injection,
                verify_cmd=verify_cmd,
                wait_seconds=3.0
            )
            for cand_id, lab_id, inj_out, verify_out in raw_results:
                lab_results_map[cand_id] = (lab_id, inj_out, verify_out)

        # 4. 결과 채점 및 Raw Reward 산출
        eval_results = []
        for cand in candidates:
            if cand.candidate_id in lab_results_map:
                lab_id, inj_out, verify_out = lab_results_map[cand.candidate_id]
            else:
                lab_id, inj_out, verify_out = "mock_lab", "", ""

            res = self.evaluator.evaluate_output(
                candidate=cand,
                lab_id=lab_id,
                injection_output=inj_out,
                show_output=verify_out,
                scenario=scenario
            )
            eval_results.append(res)

        eval_results.sort(key=lambda x: x.candidate_id)
        raw_rewards = [res.raw_reward for res in eval_results]

        # 5. GRPO Relative Advantage 계산: (raw_reward - mean) / (std + 1e-8)
        advantages = calculate_grpo_advantages(raw_rewards)

        # 6. 사용자 지정 JSONL 데이터셋 규격 생성
        group_outputs = []
        for res, adv in zip(eval_results, advantages):
            group_outputs.append(
                GroupOutputItem(
                    output=res.output_text,
                    raw_reward=res.raw_reward,
                    relative_advantage=round(adv, 2),
                    status=res.status
                )
            )

        prompt_str = f"{scenario.task_description} (현재 상태: {scenario.current_state})"

        record = GRPOScenarioRecord(
            scenario_id=scenario.scenario_id,
            prompt=prompt_str,
            group_outputs=group_outputs
        )

        logger.info(
            f"[{scenario.scenario_id}] Raw Rewards: {raw_rewards} | "
            f"Relative Advantages: {[o.relative_advantage for o in group_outputs]}"
        )
        return record

    async def run_pipeline(
        self,
        scenarios: List[Scenario],
        output_jsonl_path: str,
        candidate_count: int = 4
    ) -> List[GRPOScenarioRecord]:
        """전체 시나리오 일괄 수집 및 JSONL 저장"""
        records = []
        out_path = Path(output_jsonl_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)

        with open(out_path, "w", encoding="utf-8") as f:
            for sc in scenarios:
                record = await self.process_scenario(sc, candidate_count=candidate_count)
                records.append(record)
                f.write(json.dumps(record.to_dict(), ensure_ascii=False) + "\n")
                f.flush()

        logger.info(f"Successfully collected {len(records)} GRPO records saved to {output_jsonl_path}")
        return records
