import argparse
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SUITE_PATH = ROOT / "data/lab-transfer/scenarios_v1.json"
SUMMARY_PATH = ROOT / "data/lab-transfer/lab_validation_summary.json"
RESULTS_DIR = ROOT / "data/lab-transfer/results"
OUTPUT_PATH = ROOT / "data/sft/lab-transfer-train-v1.jsonl"
MANIFEST_PATH = ROOT / "data/sft/lab-transfer-train-v1.manifest.json"
REQUIRED_PASS_FIELDS = (
    "setup_status",
    "cli_status",
    "required_settings_status",
    "preservation_status",
    "rollback_status",
)


def load_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(
        description="Export verified L2 transfer references as an SFT JSONL dataset."
    )
    parser.add_argument(
        "--force", action="store_true", help="Overwrite existing export files."
    )
    args = parser.parse_args()

    if not args.force and (OUTPUT_PATH.exists() or MANIFEST_PATH.exists()):
        raise SystemExit("Export exists; pass --force to replace it.")

    suite = load_json(SUITE_PATH)
    summary = load_json(SUMMARY_PATH)
    rows = []
    functional_ids = []
    configuration_only_ids = []
    excluded = []

    for case in suite["cases"]:
        scenario_id = case["scenario_id"]
        result_path = RESULTS_DIR / f"result_{scenario_id}.json"
        if not result_path.is_file():
            raise ValueError(f"Missing result for {scenario_id}")

        result = load_json(result_path)
        if result.get("scenario_id") != scenario_id:
            raise ValueError(f"Scenario ID mismatch in {result_path.name}")
        if result.get("candidate_kind") != "reference":
            raise ValueError(f"Non-reference candidate in {result_path.name}")
        if result.get("raw_response") not in (None, ""):
            raise ValueError(f"Unexpected model response in {result_path.name}")

        if result.get("final_status") == "blocked":
            excluded.append({"scenario_id": scenario_id, "status": "blocked"})
            continue
        if result.get("final_status") != "pass":
            raise ValueError(f"Non-passing result in {result_path.name}")

        for field in REQUIRED_PASS_FIELDS:
            if result.get(field) != "pass":
                raise ValueError(f"{field} is not pass in {result_path.name}")

        commands = result.get("commands")
        allowed_commands = [case["reference_commands"]]
        allowed_commands.extend(case.get("allowed_alternatives", []))
        if not isinstance(commands, list) or commands not in allowed_commands:
            raise ValueError(f"Commands do not match an accepted answer for {scenario_id}")

        functional_status = result.get("functional_status")
        if functional_status == "pass":
            functional_ids.append(scenario_id)
        elif functional_status in ("not_run", "not_applicable"):
            configuration_only_ids.append(scenario_id)
        else:
            raise ValueError(
                f"Unexpected functional status {functional_status!r} for {scenario_id}"
            )

        answer = (
            "<think>\n"
            "요청 대상과 변경 범위를 확인하고, 명시된 설정 외에는 유지합니다.\n"
            "</think>\n"
            "<commands>\n"
            f"{chr(10).join(commands)}\n"
            "</commands>"
        )
        rows.append(
            {
                "scenario_id": scenario_id,
                "messages": [
                    {"role": "system", "content": suite["common_prompt"]},
                    {
                        "role": "user",
                        "content": f"대상 장비: {case['target']}\n{case['prompt']}",
                    },
                    {"role": "assistant", "content": answer},
                ],
            }
        )

    if len(suite["cases"]) != summary["total"]:
        raise ValueError("Scenario count does not match the validation summary")
    if len(rows) != summary["passed"]:
        raise ValueError("Export count does not match the validation summary")
    if len(excluded) != summary["blocked"]:
        raise ValueError("Blocked count does not match the validation summary")
    if len(functional_ids) != summary["functional_verified"]:
        raise ValueError("Functional count does not match the validation summary")
    if len(configuration_only_ids) != summary["configuration_only"]:
        raise ValueError("Configuration-only count does not match the validation summary")

    OUTPUT_PATH.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )
    manifest = {
        "dataset_id": "L2_TRANSFER_V1_SFT_REFERENCE",
        "suite_id": suite["suite_id"],
        "source_files": {
            "scenarios_v1.json": sha256(SUITE_PATH),
            "lab_validation_summary.json": sha256(SUMMARY_PATH),
        },
        "source_result_kind": "reference commands; no model responses",
        "raw_device_evidence_included": False,
        "included_count": len(rows),
        "functional_verified_ids": functional_ids,
        "configuration_only_ids": configuration_only_ids,
        "excluded": excluded,
        "suite_approval_status": suite.get("approval_status"),
        "suite_metadata_lab_validation_status": suite.get("lab_validation_status"),
        "suite_metadata_model_response_status": suite.get("model_response_status"),
        "output_file": OUTPUT_PATH.relative_to(ROOT).as_posix(),
    }
    MANIFEST_PATH.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        f"Wrote {len(rows)} SFT rows to {OUTPUT_PATH.relative_to(ROOT)} "
        f"({len(functional_ids)} functional, "
        f"{len(configuration_only_ids)} configuration-only); "
        f"excluded {len(excluded)} blocked result(s)."
    )


if __name__ == "__main__":
    main()