import io
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

import tcc_llm_assist


class TccLlmAssistCliTest(unittest.TestCase):
    def test_status_does_not_require_review_file_or_print_tokens(self):
        env_names = [
            "NVIDIA_API_KEY",
            "NVIDIA_MODEL_CHAT",
            "CEREBRAS_API_KEY",
            "GROQ_API_KEY",
            "DASHSCOPE_API_KEY",
            "DASHSCOPE_MODEL_CHAT",
            "DASHSCOPE_MODEL_VISION",
            "DASHSCOPE_MODEL_VISION_FALLBACK",
            "DASHSCOPE_FREE_QUOTA_ONLY_CONFIRMED",
            "NVIDIA_MODEL_VISION",
        ]
        previous_env = {name: os.environ.get(name) for name in env_names}
        for name in env_names:
            os.environ.pop(name, None)

        try:
            with tempfile.TemporaryDirectory() as tmp:
                env_file = Path(tmp) / ".env"
                env_file.write_text(
                    "\n".join(
                        [
                            "NVIDIA_API_KEY=fake-secret-status",
                            "NVIDIA_MODEL_CHAT=fake-model",
                            "CEREBRAS_API_KEY=fake-cerebras",
                            "DASHSCOPE_API_KEY=fake-dashscope",
                            "DASHSCOPE_MODEL_CHAT=fake-qwen",
                            "DASHSCOPE_FREE_QUOTA_ONLY_CONFIRMED=1",
                        ]
                    ),
                    encoding="utf-8",
                )
                stdout = io.StringIO()
                with patch(
                    "sys.argv",
                    [
                        "tcc_llm_assist.py",
                        "--status",
                        "--env-file",
                        str(env_file),
                        "--provider-order",
                        "dashscope,nvidia,cerebras,groq",
                    ],
                ), redirect_stdout(stdout):
                    tcc_llm_assist.main()

                output = stdout.getvalue()

            self.assertIn("nvidia", output)
            self.assertIn("dashscope", output)
            self.assertIn("DASHSCOPE_API_KEY=sim", output)
            self.assertIn("model=fake-qwen", output)
            self.assertIn("NVIDIA_API_KEY=sim", output)
            self.assertIn("model=fake-model", output)
            self.assertNotIn("fake-secret-status", output)
            self.assertNotIn("fake-dashscope", output)
        finally:
            for name, value in previous_env.items():
                if value is None:
                    os.environ.pop(name, None)
                else:
                    os.environ[name] = value

    def test_configured_vision_candidates_use_ocr_order_and_guard(self):
        env_names = [
            "NVIDIA_API_KEY",
            "NVIDIA_MODEL_VISION",
            "DASHSCOPE_API_KEY",
            "DASHSCOPE_MODEL_VISION",
            "DASHSCOPE_MODEL_VISION_FALLBACK",
            "DASHSCOPE_FREE_QUOTA_ONLY_CONFIRMED",
        ]
        previous_env = {name: os.environ.get(name) for name in env_names}
        for name in env_names:
            os.environ.pop(name, None)

        try:
            with tempfile.TemporaryDirectory() as tmp:
                env_file = Path(tmp) / ".env"
                env_file.write_text(
                    "\n".join(
                        [
                            "DASHSCOPE_API_KEY=fake-dashscope",
                            "DASHSCOPE_MODEL_VISION=fake-qwen-ocr",
                            "DASHSCOPE_MODEL_VISION_FALLBACK=fake-qwen-omni",
                            "DASHSCOPE_FREE_QUOTA_ONLY_CONFIRMED=1",
                            "NVIDIA_API_KEY=fake-nvidia",
                            "NVIDIA_MODEL_VISION=fake-nvidia-vlm",
                        ]
                    ),
                    encoding="utf-8",
                )

                candidates = tcc_llm_assist.configured_vision_candidates(
                    "dashscope,nvidia",
                    env_file,
                )

            self.assertEqual(
                ["fake-qwen-ocr", "fake-qwen-omni", "fake-nvidia-vlm"],
                [candidate.model for candidate in candidates[:3]],
            )
            self.assertEqual("DASHSCOPE_MODEL_VISION", candidates[0].model_env)
            self.assertEqual("NVIDIA_MODEL_VISION", candidates[2].model_env)

            os.environ["DASHSCOPE_FREE_QUOTA_ONLY_CONFIRMED"] = "0"
            guarded = tcc_llm_assist.configured_vision_candidates("dashscope,nvidia")
            self.assertTrue(all(candidate.provider != "dashscope" for candidate in guarded))
        finally:
            for name, value in previous_env.items():
                if value is None:
                    os.environ.pop(name, None)
                else:
                    os.environ[name] = value


if __name__ == "__main__":
    unittest.main()
