"""Test section 0 infrastructure in temporary repositories; no research code."""
import contextlib
import io
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch
from importlib import metadata

ROOT = Path(__file__).resolve().parents[1]
NOTEBOOK_NAME = "ARIN7101_Context_Bandit_Release_Notebook.ipynb"
NB = json.loads((ROOT / NOTEBOOK_NAME).read_text(encoding="utf-8"))
ENV_SOURCE = next("".join(c["source"]) for c in NB["cells"] if c["id"] == "shared-environment-check")
PATH_SOURCE = next("".join(c["source"]) for c in NB["cells"] if c["id"] == "shared-paths-and-draft")


class SetupTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="arin_setup_")
        self.addCleanup(temporary.cleanup)
        self.addCleanup(os.chdir, Path.cwd())
        self.root = Path(temporary.name) / "cloned_project"
        self.root.mkdir()
        (self.root / NOTEBOOK_NAME).write_text("{}", encoding="utf-8")
        shutil.copy2(ROOT / "requirements.txt", self.root / "requirements.txt")
        os.chdir(self.root)
        self.ns = {}
        with contextlib.redirect_stdout(io.StringIO()), patch("IPython.display.display"):
            exec(ENV_SOURCE, self.ns)
            exec(PATH_SOURCE, self.ns)

    def test_repeat_initialization_preserves_files(self):
        env_path = self.ns["CONFIG_DIR"] / "environment.json"
        before = env_path.read_bytes()
        note = self.ns["TEAM_DIR"] / "member_note.txt"
        note.write_text("human content", encoding="utf-8")
        with contextlib.redirect_stdout(io.StringIO()):
            exec(PATH_SOURCE, self.ns)
        self.assertEqual(env_path.read_bytes(), before)
        self.assertEqual(note.read_text(encoding="utf-8"), "human content")
        self.assertTrue(all(p.is_dir() for p in self.ns["RUN_PATHS"].values()))

    def test_save_helpers_refuse_overwrite(self):
        path = self.ns["artifact_path"]("development", "local_setup", "audit", "checks.json")
        self.ns["save_json"](path, {"value": 1})
        with self.assertRaises(FileExistsError):
            self.ns["save_json"](path, {"value": 2})
        self.assertEqual(json.loads(path.read_text(encoding="utf-8")), {"value": 1})
        path = self.ns["TABLES_DIR"] / "fixture.csv"
        frame = self.ns["pd"].DataFrame({"value": [1]})
        self.ns["save_csv"](path, frame)
        with self.assertRaises(FileExistsError):
            self.ns["save_csv"](path, frame)
        self.assertEqual(path.read_text(encoding="utf-8"), "value\n1\n")
        invalid = self.ns["AUDIT_DIR"] / "invalid.json"
        with self.assertRaises(ValueError):
            self.ns["save_json"](invalid, {"value": float("nan")})
        self.assertFalse(invalid.exists())

    def test_output_paths_stay_inside_run(self):
        for name in ["../escape", "folder/file.csv", "C:\\escape", "..", "NUL.txt", "trailing."]:
            with self.subTest(name=name), self.assertRaises(ValueError):
                self.ns["artifact_path"]("development", "local_setup", "data", name)
        with self.assertRaises(ValueError):
            self.ns["save_json"](self.root / "team_workspace" / "review.json", {})
        with self.assertRaises(ValueError):
            self.ns["artifact_path"]("unknown", "local_setup", "data", "x.json")

    def test_formal_run_cannot_be_reinitialized(self):
        run = self.ns["init_run"]("formal", "fixture_formal")
        before = (run / "config" / "environment.json").read_bytes()
        with self.assertRaises(FileExistsError):
            self.ns["init_run"]("formal", "fixture_formal")
        self.assertEqual((run / "config" / "environment.json").read_bytes(), before)

    def test_environment_change_requires_new_run(self):
        self.ns["ENVIRONMENT"]["python"] = "different-version"
        with self.assertRaises(RuntimeError):
            self.ns["init_run"]("development", "local_setup")

    def test_explicit_root_works_outside_repository(self):
        os.chdir(self.root.parent)
        source = ENV_SOURCE.replace("PROJECT_ROOT = None", f"PROJECT_ROOT = {str(self.root)!r}", 1)
        namespace = {}
        with contextlib.redirect_stdout(io.StringIO()), patch("IPython.display.display"):
            exec(source, namespace)
        self.assertEqual(namespace["ROOT"], self.root.resolve())

    def test_missing_dependency_install_and_restart(self):
        original_version = metadata.version

        def missing_numpy(name):
            if name == "numpy":
                raise metadata.PackageNotFoundError(name)
            return original_version(name)

        with contextlib.redirect_stdout(io.StringIO()), patch("importlib.metadata.version", side_effect=missing_numpy), patch("subprocess.run") as install:
            with self.assertRaises(RuntimeError):
                exec(ENV_SOURCE, {})
            argv = install.call_args.args[0]
            self.assertEqual(argv[:4], [self.ns["sys"].executable, "-m", "pip", "install"])
            self.assertEqual(argv[-1], str(self.root / "requirements.txt"))
            install.assert_called_once()

    def test_check_only_does_not_install(self):
        source = ENV_SOURCE.replace("AUTO_INSTALL_MISSING = True", "AUTO_INSTALL_MISSING = False", 1)
        with contextlib.redirect_stdout(io.StringIO()), patch("importlib.metadata.version", side_effect=metadata.PackageNotFoundError), patch("subprocess.run") as install:
            with self.assertRaises(RuntimeError):
                exec(source, {})
            install.assert_not_called()


if __name__ == "__main__":
    unittest.main(verbosity=2)
