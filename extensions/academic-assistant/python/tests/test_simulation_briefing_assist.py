import json
import os
import tempfile
import unittest
from pathlib import Path

import simulation_briefing_assist as briefing


class SimulationBriefingAssistTest(unittest.TestCase):
    def test_dry_run_generates_internal_prd_epics_and_story_without_spending_tokens(self):
        env_names = [
            "NVIDIA_API_KEY",
            "NVIDIA_MODEL_CHAT",
            "CEREBRAS_API_KEY",
            "CEREBRAS_MODEL_CHAT",
            "GROQ_API_KEY",
            "GROQ_MODEL_COMPLEX",
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
                            "CEREBRAS_MODEL_CHAT=fake-cerebras-model",
                            "GROQ_API_KEY=fake-groq",
                            "GROQ_MODEL_COMPLEX=fake-groq-model",
                        ]
                    ),
                    encoding="utf-8",
                )
                output_dir = tmp_path / "briefing"
                idea = (
                    "Quero simular um pronto atendimento hospitalar com chegada, "
                    "triagem, consulta, exames opcionais e alta."
                )

                result = briefing.main(
                    [
                        "--idea",
                        idea,
                        "--case-id",
                        "pa_hospitalar",
                        "--output-dir",
                        str(output_dir),
                        "--env-file",
                        str(env_file),
                    ]
                )

                payload_path = output_dir / "pa_hospitalar_briefing_assist.json"
                consolidated_path = output_dir / "pa_hospitalar_briefing_assist.md"
                prd_path = output_dir / "pa_hospitalar_prd_interno.md"
                epics_path = output_dir / "pa_hospitalar_epicos_stories.md"
                history_path = output_dir / "pa_hospitalar_historia_simulacao.md"

                payload = json.loads(payload_path.read_text(encoding="utf-8"))
                consolidated = consolidated_path.read_text(encoding="utf-8")
                prd = prd_path.read_text(encoding="utf-8")
                epics = epics_path.read_text(encoding="utf-8")
                history = history_path.read_text(encoding="utf-8")

            self.assertEqual(0, result)
            self.assertFalse(payload["metadata"]["online"])
            self.assertIn("dry_run", json.dumps(payload["metadata"], ensure_ascii=False))
            self.assertIn("PRD interno", prd)
            self.assertIn("Epicos e stories", epics)
            self.assertIn("Historia da simulacao", history)
            self.assertIn("Plano StatFit-like", consolidated)
            self.assertIn("A IA nao deve criar objetos", consolidated)
        finally:
            for name, value in previous_env.items():
                if value is None:
                    os.environ.pop(name, None)
                else:
                    os.environ[name] = value


if __name__ == "__main__":
    unittest.main()
