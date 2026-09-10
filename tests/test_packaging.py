"""Offline packaging regression tests: strict locks, environment scope, fail-closed audit."""
from pathlib import Path
import re
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from scripts import dependency_check as check
from scripts import install_dependencies as installer
from scripts import refresh_dependency_lock as refresh


class LockTests(unittest.TestCase):
    def parse(self, content, **options):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "requirements.txt"
            path.write_text(content, encoding="utf-8")
            return check.read_pins(path, **options)

    def test_exact_pins_and_hashes_are_normalized(self):
        pins = self.parse("# Comment\nSome_Package==1.2.3 \\" + "\n    --hash=sha256:" + "a" * 64 + "\n")
        self.assertEqual(pins, {"some-package": {"version": "1.2.3", "hashes": ["a" * 64]}})

    def test_unreviewed_requirement_forms_fail(self):
        cases = ["thing>=1", "thing==1", "-r more.txt", "--extra-index-url https://example.invalid",
                 "thing @ https://example.invalid/a.whl", "thing==1 --hash=md5:" + "a" * 32,
                 "thing==1 --hash=sha256:" + "a" * 63,
                 "thing==1 ; python_version > '3.0'", "thing==1 \\\n", "# Empty\n"]
        for content in cases:
            with self.subTest(content=content), self.assertRaises(ValueError):
                self.parse(content)

    def test_duplicate_names_and_hashes_fail(self):
        line = "some_pkg==1 --hash=sha256:" + "a" * 64
        for content in (line + "\n" + line.replace("some_pkg", "Some-Pkg"),
                        line + " --hash=sha256:" + "a" * 64):
            with self.assertRaisesRegex(ValueError, "Duplicate"):
                self.parse(content)

    def test_checked_in_lock_preserves_scientific_sdk_and_security_floors(self):
        pins = check.reviewed_pins()
        self.assertEqual(len(pins), 63)
        self.assertEqual(pins["alphagenome"]["version"], "0.8.0")
        self.assertEqual(pins["pip"]["version"], "26.2.1")
        self.assertEqual(pins["setuptools"]["version"], "84.0.0")

    def test_exact_installed_inventory_includes_installers(self):
        pins = {"thing": {"version": "1"}}
        exact = SimpleNamespace(metadata={"Name": "Thing"}, version="1")
        check.verify_installed(pins, [exact])
        for distributions in ([], [exact, exact],
                              [SimpleNamespace(metadata={"Name": "Thing"}, version="2")],
                              [exact, SimpleNamespace(metadata={"Name": "extra"}, version="1")]):
            with self.assertRaises(ValueError):
                check.verify_installed(pins, distributions)


class AdvisoryTests(unittest.TestCase):
    pins = {"pip": {"version": "26.2.1"}, "alphagenome": {"version": "0.8.0"}}

    def test_only_public_names_and_versions_are_sent(self):
        sent = []
        def request(url, payload):
            sent.append((url, payload))
            return {"results": [{}, {}]}
        self.assertEqual(check.query_advisories(self.pins, request), {})
        url, payload = sent[0]
        self.assertEqual(url, "https://api.osv.dev/v1/querybatch")
        self.assertEqual(payload, {"queries": [
            {"package": {"name": "alphagenome", "ecosystem": "PyPI"}, "version": "0.8.0"},
            {"package": {"name": "pip", "ecosystem": "PyPI"}, "version": "26.2.1"}]})

    def test_findings_are_not_suppressed(self):
        found = check.query_advisories(self.pins, lambda *args: {
            "results": [{"vulns": [{"id": "EXAMPLE-1"}]}, {}]})
        self.assertEqual(found, {"alphagenome": ["EXAMPLE-1"]})

    def test_incomplete_error_and_paginated_results_fail_closed(self):
        for result in ({}, {"results": []}, {"results": [{}, {"next_page_token": "more"}]},
                       {"results": [{}, {"error": "error"}]}, {"results": [{}, {"vulns": [None]}]},
                       {"results": [{}, {"vulns": "invalid"}]}):
            with self.subTest(result=result), self.assertRaises(ValueError):
                check.query_advisories(self.pins, lambda *args: result)

    def test_network_failure_is_not_a_clean_result(self):
        with patch.object(check.urllib.request, "urlopen", side_effect=OSError("offline")) as mocked:
            with self.assertRaisesRegex(RuntimeError, "no clean result"):
                check.request_json("https://api.osv.dev/v1/querybatch", {})
        self.assertEqual(mocked.call_count, 2)

    def test_advisory_cli_returns_nonzero_on_finding(self):
        with patch.object(check.sys, "argv", ["dependency_check", "--advisories"]), \
             patch.object(check, "query_advisories", return_value={"pip": ["EXAMPLE-1"]}), \
             patch("builtins.print"):
            self.assertEqual(check.main(), 1)


class InstallerTests(unittest.TestCase):
    def test_install_sequence_enforces_hashes_wheels_and_exact_inventory(self):
        pins = check.reviewed_pins()
        with patch.object(installer, "validate_environment"), \
             patch.object(installer, "verify_installed") as inventory, \
             patch.object(installer.subprocess, "run") as run, \
             patch.dict(installer.os.environ, {"PIP_TARGET": "outside", "PIP_NO_REQUIRE_HASHES": "1",
                                               "PIP_EXTRA_INDEX_URL": "https://example.invalid", "PYTHONPATH": "outside"}), \
             patch("builtins.print"):
            installer.install_environment()
        self.assertEqual(run.call_count, 3)
        for call, filename in zip(run.call_args_list[:2], check.LOCKS):
            command = call.args[0]
            for argument in ("--require-hashes", "--only-binary=:all:", "--no-deps", "https://pypi.org/simple"):
                self.assertIn(argument, command)
            self.assertEqual(Path(command[-1]).name, filename)
            environment = call.kwargs["env"]
            self.assertEqual({key for key in environment if key.startswith("PIP_")}, {"PIP_CONFIG_FILE"})
            self.assertEqual(environment["PIP_CONFIG_FILE"], installer.os.devnull)
            self.assertNotIn("PYTHONPATH", environment)
            self.assertTrue(call.kwargs["check"])
        self.assertEqual(run.call_args_list[-1].args[0][-1], "check")
        inventory.assert_called_once_with(pins)

    def test_environment_refusal_precedes_any_install(self):
        with patch.object(installer, "validate_environment", side_effect=ValueError("wrong venv")), \
             patch.object(installer.subprocess, "run") as run:
            with self.assertRaises(ValueError):
                installer.install_environment()
            run.assert_not_called()

    def test_foreign_or_symlinked_environment_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaisesRegex(ValueError, "dedicated"):
                installer.validate_environment(root)
            (root / ".venv").symlink_to(Path(installer.sys.prefix), target_is_directory=True)
            with self.assertRaisesRegex(ValueError, "dedicated"):
                installer.validate_environment(root)

    def test_system_site_packages_and_redirected_install_paths_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            environment = root / ".venv"
            environment.mkdir()
            config = environment / "pyvenv.cfg"
            with patch.object(installer.sys, "prefix", str(environment)), \
                 patch.object(installer.sysconfig, "get_path", return_value=str(root / "elsewhere")):
                config.write_text("include-system-site-packages = true\n# include-system-site-packages = false\n")
                with self.assertRaisesRegex(ValueError, "system site"):
                    installer.validate_environment(root)
                config.write_text("include-system-site-packages = false\n")
                with self.assertRaisesRegex(ValueError, "install paths"):
                    installer.validate_environment(root)

    def test_install_failure_does_not_continue(self):
        with patch.object(installer, "validate_environment"), \
             patch.object(installer.subprocess, "run", side_effect=installer.subprocess.CalledProcessError(1, ["pip"])) as run, \
             patch.object(installer, "verify_installed") as inventory:
            with self.assertRaises(installer.subprocess.CalledProcessError):
                installer.install_environment()
        self.assertEqual(run.call_count, 1)
        inventory.assert_not_called()

    def test_workflow_actions_are_sha_pinned_and_uses_setup(self):
        workflow = (check.ROOT / ".github/workflows/offline-tests.yml").read_text()
        actions = re.findall(r"uses: ([^\s]+)", workflow)
        self.assertEqual(len(actions), 3)
        self.assertTrue(all(re.fullmatch(r"actions/[a-z-]+@[a-f0-9]{40}", action) for action in actions))
        self.assertIn("persist-credentials: false", workflow)
        self.assertIn("bash scripts/setup.sh", workflow)
        self.assertIn("--installed --advisories", workflow)
        for platform in ("ubuntu-24.04", "ubuntu-24.04-arm", "macos-14", "macos-15-intel"):
            self.assertIn(platform, workflow)


class WheelReviewTests(unittest.TestCase):
    def test_native_windows_musl_and_unreviewed_architectures_excluded(self):
        for platform in ("win_amd64", "musllinux_1_2_x86_64", "linux_armv7l", "manylinux2014_s390x"):
            self.assertFalse(refresh.allowed_platform(platform))
        for platform in ("any", "macosx_12_0_arm64", "macosx_10_9_universal2", "manylinux_2_28_x86_64"):
            self.assertTrue(refresh.allowed_platform(platform))

    def metadata(self, *, yanked=False, filename="thing-1.0-py3-none-any.whl"):
        return {"info": {"name": "thing", "version": "1.0"}, "urls": [{
            "filename": filename, "packagetype": "bdist_wheel", "yanked": yanked,
            "requires_python": ">=3.11", "digests": {"sha256": "a" * 64}}]}

    def test_universal_wheel_covers_all_four_targets(self):
        self.assertEqual(refresh.wheel_hashes(("thing", {"version": "1.0"}), lambda url: self.metadata()),
                         ("thing", "1.0", ["a" * 64]))

    def test_yanked_and_incomplete_platform_coverage_fail(self):
        for metadata in (self.metadata(yanked=True), self.metadata(filename="thing-1.0-cp311-cp311-macosx_12_0_arm64.whl")):
            with self.assertRaisesRegex(ValueError, "No compatible"):
                refresh.wheel_hashes(("thing", {"version": "1.0"}), lambda url: metadata)

    def test_newer_python_only_wheel_fails(self):
        metadata = self.metadata(filename="thing-1.0-cp312-cp312-manylinux_2_28_x86_64.whl")
        with self.assertRaisesRegex(ValueError, "No compatible"):
            refresh.wheel_hashes(("thing", {"version": "1.0"}), lambda url: metadata)


if __name__ == "__main__":
    unittest.main()
