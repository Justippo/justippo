"""Unit tests for the isolated BabelDOC subprocess bridge."""

from __future__ import annotations

import asyncio
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from app.runtime import (
    BabelDocConfigError,
    BabelDocInvalidInputError,
    BabelDocRuntimeConfig,
    BabelDocRuntimeError,
    _build_command,
    _run_command,
    _write_runtime_config,
    get_runtime_config,
    run_babeldoc_translation,
)


class RuntimeCommandTests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = BabelDocRuntimeConfig(
            openai_base_url="https://gateway.ai.cloudflare.com/v1/account/gateway/compat",
            openai_api_key="private-gateway-key",
            openai_model="@cf/meta/llama-4-scout-17b-16e-instruct",
        )

    def test_secret_is_stored_in_restricted_config_not_argv(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            work_dir = Path(temp_dir)
            input_pdf = work_dir / "input.pdf"
            input_pdf.write_bytes(b"%PDF")
            config_path = _write_runtime_config(config=self.config, work_dir=work_dir)
            command = _build_command(
                input_pdf=input_pdf,
                work_dir=work_dir,
                glossary_path=None,
                source_lang="en",
                target_lang="de",
                timeout_options={},
                runtime_config_path=config_path,
            )

            self.assertNotIn(self.config.openai_api_key, command)
            self.assertIn("--config", command)
            self.assertIn(self.config.openai_api_key, config_path.read_text())
            self.assertEqual(config_path.stat().st_mode & 0o777, 0o600)
            output_index = command.index("--output") + 1
            self.assertTrue(Path(command[output_index]).is_dir())

    def test_command_includes_supported_limits_and_glossary(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            work_dir = Path(temp_dir)
            input_pdf = work_dir / "input.pdf"
            glossary = work_dir / "glossary.csv"
            config_path = work_dir / "babeldoc.toml"
            command = _build_command(
                input_pdf=input_pdf,
                work_dir=work_dir,
                glossary_path=glossary,
                source_lang="fr",
                target_lang="en",
                timeout_options={"qps": 2, "max_pages": 10, "watermark": True},
                runtime_config_path=config_path,
            )

            self.assertIn("1-10", command)
            self.assertIn("watermarked", command)
            self.assertIn(str(glossary), command)

    def test_command_enables_compatibility_mode_for_form_pdfs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            work_dir = Path(temp_dir)
            command = _build_command(
                input_pdf=work_dir / "input.pdf",
                work_dir=work_dir,
                glossary_path=None,
                source_lang="de",
                target_lang="fr",
                timeout_options={},
                runtime_config_path=work_dir / "babeldoc.toml",
            )

            self.assertIn("--enhance-compatibility", command)
            min_text_length_index = command.index("--min-text-length") + 1
            self.assertEqual(command[min_text_length_index], "2")

    def test_unknown_option_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            work_dir = Path(temp_dir)
            with self.assertRaises(BabelDocInvalidInputError):
                _build_command(
                    input_pdf=work_dir / "input.pdf",
                    work_dir=work_dir,
                    glossary_path=None,
                    source_lang="en",
                    target_lang="de",
                    timeout_options={"shell": "unsafe"},
                    runtime_config_path=work_dir / "babeldoc.toml",
                )

    def test_qps_and_page_limits_are_enforced(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            work_dir = Path(temp_dir)
            for options in (
                {"qps": 17},
                {"max_pages": 21},
                {"watermark": "false"},
                {"enhance_compatibility": "true"},
                {"min_text_length": 0},
                {"min_text_length": "two"},
            ):
                with self.subTest(options=options), self.assertRaises(BabelDocInvalidInputError):
                    _build_command(
                        input_pdf=work_dir / "input.pdf",
                        work_dir=work_dir,
                        glossary_path=None,
                        source_lang="en",
                        target_lang="de",
                        timeout_options=options,
                        runtime_config_path=work_dir / "babeldoc.toml",
                    )

    def test_gateway_lookalike_host_is_rejected(self) -> None:
        with (
            patch.dict(
                os.environ,
                {
                    "BABELDOC_OPENAI_BASE_URL": (
                        "https://gateway.ai.cloudflare.com.attacker.example/v1"
                    ),
                    "BABELDOC_OPENAI_API_KEY": "secret",
                    "BABELDOC_OPENAI_MODEL": "model",
                },
                clear=True,
            ),
            self.assertRaises(BabelDocConfigError),
        ):
            get_runtime_config()

    def test_request_workspace_is_removed_after_runtime_failure(self) -> None:
        original_temporary_directory = tempfile.TemporaryDirectory
        created_paths: list[Path] = []

        def tracked_temporary_directory(*args, **kwargs):
            temporary_directory = original_temporary_directory(*args, **kwargs)
            created_paths.append(Path(temporary_directory.name))
            return temporary_directory

        with (
            patch("app.runtime.get_runtime_config", return_value=self.config),
            patch(
                "app.runtime.tempfile.TemporaryDirectory",
                side_effect=tracked_temporary_directory,
            ),
            patch(
                "app.runtime._run_command",
                new=AsyncMock(side_effect=BabelDocRuntimeError("failed")),
            ),
            self.assertRaises(BabelDocRuntimeError),
        ):
            asyncio.run(
                run_babeldoc_translation(
                    document=b"%PDF-1.7",
                    glossary_rows=[],
                    source_lang="en",
                    target_lang="de",
                    preserve_layout=True,
                    timeout_seconds=30,
                    options={},
                )
            )

        self.assertEqual(len(created_paths), 1)
        self.assertFalse(created_paths[0].exists())


class RuntimeProcessTests(unittest.TestCase):
    def test_nonzero_exit_never_exposes_subprocess_output(self) -> None:
        process = AsyncMock()
        process.communicate.return_value = (b"", b"private document text")
        process.returncode = 1

        with (
            patch(
                "app.runtime.asyncio.create_subprocess_exec",
                new=AsyncMock(return_value=process),
            ),
            self.assertRaises(BabelDocRuntimeError) as exc_info,
        ):
            asyncio.run(_run_command(["babeldoc"], timeout_seconds=10))

        self.assertNotIn("private document text", str(exc_info.exception))

    def test_missing_executable_maps_to_service_unavailable(self) -> None:
        with (
            patch(
                "app.runtime.asyncio.create_subprocess_exec",
                new=AsyncMock(side_effect=FileNotFoundError("babeldoc")),
            ),
            self.assertRaises(BabelDocConfigError),
        ):
            asyncio.run(_run_command(["babeldoc"], timeout_seconds=10))


if __name__ == "__main__":
    unittest.main()
