import json
import os
import tempfile
import unittest
from pathlib import Path

import modulo_ia_offline as offline


class ModuloIaOfflineTest(unittest.TestCase):
    def test_reviews_snapshot_without_expected_matrix_or_ai(self):
        snapshot = (
            offline.snapshot_analyzer.CASES_DIR
            / "c1_fila_simples_inconsistente.json"
        )

        with tempfile.TemporaryDirectory() as tmp:
            result = offline.review_input(snapshot, Path(tmp))
            payload = json.loads((Path(tmp) / f"{result.analysis.model_id}_offline_review.json").read_text(encoding="utf-8"))
            markdown = (Path(tmp) / f"{result.analysis.model_id}_offline_review.md").read_text(encoding="utf-8")
            suggestion_status = json.loads((Path(tmp) / f"{result.analysis.model_id}_suggestions_status.json").read_text(encoding="utf-8"))
            change_plan = json.loads((Path(tmp) / f"{result.analysis.model_id}_allowed_changes_plan.json").read_text(encoding="utf-8"))
            audit = json.loads((Path(tmp) / f"{result.analysis.model_id}_suggestion_decision_audit.json").read_text(encoding="utf-8"))

        self.assertEqual("json", result.input_type)
        self.assertIsNone(result.generated_snapshot_file)
        self.assertIn("suggestions_status.json", result.output_suggestions_file)
        self.assertIn("allowed_changes_plan.json", result.output_change_plan_file)
        self.assertIn("suggestion_decision_audit.json", result.output_audit_file)
        self.assertIsNone(result.output_llm_assist_json_file)
        self.assertIsNone(result.output_llm_assist_markdown_file)
        self.assertIsNone(result.output_reviewed_snapshot_file)
        self.assertEqual({"RCL03", "RCL04", "RCL07", "RCL10"}, set(offline.triggered_rules(result.analysis)))
        self.assertEqual(4, len(result.local_suggestions))
        self.assertEqual([], result.allowed_changes)
        self.assertEqual(4, len(result.suggestion_audit))
        self.assertEqual("associate_or_remove_resource", result.local_suggestions[0].action_type)
        self.assertEqual("suggestion_only", result.local_suggestions[0].automation_policy)
        self.assertEqual("pending", result.local_suggestions[0].status)
        self.assertEqual("generated_default", result.suggestion_audit[0].status_source)
        self.assertEqual("aguarda_decisao_humana", result.suggestion_audit[0].decision_effect)
        self.assertEqual([], result.analysis.false_positives)
        self.assertFalse(payload["ai_usage"]["internet_api"])
        self.assertFalse(payload["ai_usage"]["llm_online"])
        self.assertFalse(payload["ai_usage"]["local_ai"])
        self.assertFalse(payload["llm_online_assist"]["enabled"])
        self.assertIn("suggestion_decision_audit_file", payload)
        self.assertEqual(4, len(payload["local_suggestions"]))
        self.assertEqual(4, len(payload["suggestion_decision_audit"]))
        self.assertEqual([], payload["allowed_changes"])
        self.assertEqual(4, len(suggestion_status["suggestions"]))
        self.assertEqual([], change_plan["allowed_changes"])
        self.assertEqual(4, len(audit["audit_entries"]))
        self.assertEqual(["accepted", "applied", "cancelled", "pending", "rejected"], suggestion_status["allowed_statuses"])
        self.assertIn("offline_deterministico", markdown)
        self.assertIn("Status das sugestoes", markdown)
        self.assertIn("Sugestoes locais estruturadas", markdown)
        self.assertIn("Ledger de decisoes", markdown)
        self.assertIn("IA local: `nao utilizada`", markdown)

    def test_optional_llm_assist_dry_run_uses_ranked_local_providers(self):
        snapshot = (
            offline.snapshot_analyzer.CASES_DIR
            / "c1_fila_simples_inconsistente.json"
        )

        env_names = [
            "NVIDIA_API_KEY",
            "NVIDIA_MODEL_CHAT",
            "CEREBRAS_API_KEY",
            "CEREBRAS_MODEL_CHAT",
            "GROQ_API_KEY",
            "GROQ_MODEL_COMPLEX",
            "CHAT_PROVIDER_ORDER",
            "TCC_LLM_PROVIDER_ORDER",
        ]
        previous_env = {name: os.environ.get(name) for name in env_names}
        for name in env_names:
            os.environ.pop(name, None)

        try:
            with tempfile.TemporaryDirectory() as tmp:
                tmp_path = Path(tmp)
                env_file = tmp_path / ".env"
                env_file.write_text(
                    "\n".join(
                        [
                            "NVIDIA_API_KEY=fake-nvidia",
                            "NVIDIA_MODEL_CHAT=fake-smart-nvidia",
                            "CEREBRAS_API_KEY=fake-cerebras",
                            "CEREBRAS_MODEL_CHAT=fake-smart-cerebras",
                            "GROQ_API_KEY=fake-groq",
                            "GROQ_MODEL_COMPLEX=fake-smart-groq",
                        ]
                    ),
                    encoding="utf-8",
                )
                result = offline.review_input(
                    snapshot,
                    tmp_path,
                    llm_assist=True,
                    llm_env_file=env_file,
                    llm_provider_order="nvidia,cerebras,groq",
                    llm_dry_run=True,
                )
                llm_json = json.loads(Path(result.output_llm_assist_json_file).read_text(encoding="utf-8"))
                llm_markdown = Path(result.output_llm_assist_markdown_file).read_text(encoding="utf-8")
                offline_payload = json.loads((tmp_path / f"{result.analysis.model_id}_offline_review.json").read_text(encoding="utf-8"))
        finally:
            for name, value in previous_env.items():
                if value is None:
                    os.environ.pop(name, None)
                else:
                    os.environ[name] = value

        self.assertIn("llm_assist.json", result.output_llm_assist_json_file)
        self.assertIn("llm_assist.md", result.output_llm_assist_markdown_file)
        self.assertTrue(offline_payload["llm_online_assist"]["enabled"])
        self.assertEqual("nvidia", llm_json["provider_status"][0]["provider"])
        self.assertEqual("fake-smart-nvidia", llm_json["provider_status"][0]["model"])
        self.assertTrue(llm_json["prototype_only"])
        self.assertIn("DRY RUN", llm_markdown)

    def test_reviews_cfg_by_generating_snapshot_offline(self):
        cfg = (
            offline.snapshot_analyzer.ROOT
            / "examples"
            / "jaamsim"
            / "c1_fila_simples_inconsistente.cfg"
        )

        with tempfile.TemporaryDirectory() as tmp:
            result = offline.review_input(
                cfg,
                Path(tmp),
                model_id="c1_offline_cfg",
                case_id="OFFLINE",
                variant="review",
            )
            generated_snapshot = Path(tmp) / "snapshots" / "c1_offline_cfg_snapshot.json"
            self.assertTrue(generated_snapshot.exists())
            markdown = (Path(tmp) / "c1_offline_cfg_offline_review.md").read_text(encoding="utf-8")

        self.assertEqual("cfg", result.input_type)
        self.assertIn("snapshots/c1_offline_cfg_snapshot.json", result.generated_snapshot_file.replace("\\", "/"))
        self.assertEqual({"RCL03", "RCL04", "RCL07", "RCL10"}, set(offline.triggered_rules(result.analysis)))
        self.assertEqual(4, len(result.local_suggestions))
        self.assertIn("Tipo de entrada: `cfg`", markdown)
        self.assertIn("Internet/API: `nao utilizada`", markdown)

    def test_expected_matrix_is_optional_and_available(self):
        snapshot = (
            offline.snapshot_analyzer.CASES_DIR
            / "c2_processo_sequencial_inconsistente.json"
        )

        with tempfile.TemporaryDirectory() as tmp:
            result = offline.review_input(snapshot, Path(tmp), use_matrix=True)

        self.assertEqual(["RCL01", "RCL02", "RCL05", "RCL07", "RCL09"], result.analysis.expected_rules)
        self.assertEqual([], result.analysis.omissions)
        self.assertEqual([], result.analysis.false_positives)

    def test_rcl2_templates_generate_structured_local_suggestions(self):
        analysis = offline.snapshot_analyzer.Analysis(
            model_id="nat17",
            case_id="NAT17",
            variant="rcl2",
            snapshot_file="synthetic.json",
            alerts=[
                offline.snapshot_analyzer.Alert(
                    rule_id="RCL23",
                    severity="media",
                    component_id="rec",
                    message="capacidade ausente",
                    why_it_matters="capacidade ausente impede gargalo",
                    suggestion="definir capacidade",
                    evidence={},
                )
            ],
            expected_rules=[],
            unexpected_rules=[],
            matched_rules=[],
            omissions=[],
            false_positives=[],
        )

        suggestions = offline.build_local_suggestions(analysis)

        self.assertEqual("define_resource_capacity", suggestions[0].action_type)
        self.assertEqual("draft_only", suggestions[0].automation_policy)
        self.assertEqual("assumption", suggestions[0].scope)

    def test_experienced_profile_changes_local_guidance(self):
        snapshot = (
            offline.snapshot_analyzer.CASES_DIR
            / "c3_modelo_ambiguo_inconsistente.json"
        )

        with tempfile.TemporaryDirectory() as tmp:
            result = offline.review_input(snapshot, Path(tmp), user_profile="experienced")
            markdown = (Path(tmp) / f"{result.analysis.model_id}_offline_review.md").read_text(encoding="utf-8")
            payload = json.loads((Path(tmp) / f"{result.analysis.model_id}_offline_review.json").read_text(encoding="utf-8"))

        self.assertEqual("experienced", payload["user_profile"])
        self.assertIn("Perfil de orientacao: `experienced`", markdown)
        self.assertIn("Formalize condicao, probabilidade, prioridade ou politica de roteamento.", markdown)

    def test_status_file_tracks_accept_and_reject_without_applying_changes(self):
        snapshot = (
            offline.snapshot_analyzer.CASES_DIR
            / "c1_fila_simples_inconsistente.json"
        )

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            status_file = tmp_path / "statuses.json"
            status_file.write_text(
                json.dumps(
                    {
                        "suggestions": {
                            "SUG001": {
                                "status": "accepted",
                                "reason": "Recurso deve ser ligado ao atendimento.",
                                "actor": "operador",
                                "updated_at": "2026-05-22",
                            },
                            "SUG002": "rejected",
                        }
                    }
                ),
                encoding="utf-8-sig",
            )
            result = offline.review_input(snapshot, tmp_path, status_file=status_file)
            markdown = (tmp_path / f"{result.analysis.model_id}_offline_review.md").read_text(encoding="utf-8")
            audit = json.loads((tmp_path / f"{result.analysis.model_id}_suggestion_decision_audit.json").read_text(encoding="utf-8"))
            summary = (tmp_path / "offline_summary.csv")
            offline.write_summary([result], tmp_path)
            summary_text = summary.read_text(encoding="utf-8")

        self.assertEqual("accepted", result.local_suggestions[0].status)
        self.assertEqual("rejected", result.local_suggestions[1].status)
        self.assertEqual("status_file", result.suggestion_audit[0].status_source)
        self.assertEqual("aceita_com_guardrail_manual", result.suggestion_audit[0].decision_effect)
        self.assertEqual("rejeitada_sem_plano_de_mudanca", result.suggestion_audit[1].decision_effect)
        self.assertEqual(1, len(result.allowed_changes))
        self.assertFalse(result.allowed_changes[0].applyable)
        self.assertEqual("topology_or_resource_guardrail", result.allowed_changes[0].safety)
        self.assertEqual("topology_or_resource_guardrail", audit["audit_entries"][0]["guardrail"])
        self.assertIn("Motivo/status: Recurso deve ser ligado ao atendimento.", markdown)
        self.assertIn("accepted_suggestions", summary_text)
        self.assertIn("output_audit_file", summary_text)
        self.assertIn(",1,1,0,", summary_text)

    def test_applies_only_safe_metadata_changes_to_reviewed_snapshot(self):
        snapshot = (
            offline.snapshot_analyzer.CASES_DIR
            / "c3_modelo_ambiguo_inconsistente.json"
        )

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            status_file = tmp_path / "statuses.json"
            status_file.write_text(
                json.dumps({"suggestions": {"SUG001": "accepted", "SUG002": "accepted", "SUG003": "accepted"}}),
                encoding="utf-8",
            )
            result = offline.review_input(
                snapshot,
                tmp_path,
                status_file=status_file,
                apply_safe_changes=True,
            )
            reviewed = json.loads(Path(result.output_reviewed_snapshot_file).read_text(encoding="utf-8"))
            change_plan = json.loads((tmp_path / f"{result.analysis.model_id}_allowed_changes_plan.json").read_text(encoding="utf-8"))

        self.assertEqual(3, len(result.allowed_changes))
        self.assertEqual(3, len(result.suggestion_audit))
        self.assertEqual(2, sum(1 for change in result.allowed_changes if change.applyable))
        self.assertEqual(2, sum(1 for audit in result.suggestion_audit if audit.automatic_application))
        self.assertIsNotNone(result.output_reviewed_snapshot_file)
        self.assertEqual(2, len(reviewed["assumptions"]))
        self.assertEqual(3, len(reviewed["components"]))
        self.assertEqual(2, len(reviewed["connections"]))
        self.assertIn("topologia preservada", reviewed["notes"])
        self.assertEqual(3, len(change_plan["allowed_changes"]))


    def test_cfg_parser_warnings_reach_json_markdown_and_native_cli(self):
        import io
        import sys
        from contextlib import redirect_stdout
        from unittest.mock import patch

        cfg = """RecordEdits
Define EntityGenerator { Gen }
Define Mystery { Missing }
Gen NextComponent { Missing }
"""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "unresolved.cfg"
            path.write_text(cfg, encoding="utf-8")
            out = root / "output"
            result = offline.review_input(path, out)
            report = json.loads(Path(result.output_json_file).read_text(encoding="utf-8"))
            markdown = Path(result.output_markdown_file).read_text(encoding="utf-8")

            self.assertEqual("R001-v6-bridge", result.parser_schema_version)
            self.assertEqual(1, len(result.parser_warnings))
            self.assertEqual(
                "UNSUPPORTED_OR_UNRESOLVED_FLOW_TARGET",
                result.parser_warnings[0]["type"],
            )
            self.assertEqual("Missing", result.parser_warnings[0]["target"])
            self.assertEqual(1, report["parser_diagnostics"]["warning_count"])
            self.assertTrue(report["parser_diagnostics"]["independent_of_rcl"])
            self.assertIn("Diagnosticos do parser CFG", markdown)
            self.assertIn("UNSUPPORTED_OR_UNRESOLVED_FLOW_TARGET", markdown)

            with patch.object(sys, "argv", ["modulo_ia_offline.py", str(path), "--output-dir", str(out)]):
                stdout = io.StringIO()
                with redirect_stdout(stdout):
                    offline.main()
            self.assertIn("Diagnosticos parser: 1 avisos", stdout.getvalue())
            self.assertIn("ATENCAO: cobertura parcial de CFG", stdout.getvalue())

    def test_clean_json_review_has_no_parser_warning(self):
        snapshot = offline.snapshot_analyzer.CASES_DIR / "c1_fila_simples_referencia.json"
        with tempfile.TemporaryDirectory() as tmp:
            result = offline.review_input(snapshot, Path(tmp))
            report = json.loads(Path(result.output_json_file).read_text(encoding="utf-8"))
        self.assertEqual([], result.parser_warnings)
        self.assertEqual(0, report["parser_diagnostics"]["warning_count"])


if __name__ == "__main__":
    unittest.main()
