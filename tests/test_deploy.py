"""Exercise release failure paths with isolated Docker/HTTP command doubles."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


@unittest.skipUnless(os.name == "posix", "deployment requires Linux")
class DeploymentTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.revision = "a" * 40
        self.release = self.root / "releases" / f"{self.revision}-123-1"
        self.release.mkdir(parents=True)
        source = Path(__file__).resolve().parents[1] / "deploy"
        for name in ("release.sh", "compose.production.yaml", "compose.gateway.yaml",
                     "prepare.sh", "setup-gateway.sh", "app.env.example"):
            shutil.copyfile(source / name, self.release / name)
        shutil.copytree(source / "gateway", self.release / "gateway")
        (self.release / "image.tar.gz").touch()
        self.image = f"itmo-campus:{self.revision}-123-1"
        (self.release / "image.ref").write_text(self.image + "\n")
        (self.root / "data").mkdir()
        (self.root / ".private").mkdir()
        (self.root / ".private/.env").write_text("BOT_TOKEN=123:fixture\n")
        (self.root / ".env").write_text("CAMPUS_UID=1000\nCAMPUS_GID=1000\n")
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.command("docker", '''#!/bin/bash
echo "$CAMPUS_IMAGE $*" >> "$CAMPUS_ROOT/calls"
if [[ $* == 'image inspect '* && $3 != "$AVAILABLE_IMAGE" ]]; then
    echo "No such image: $3" >&2
    exit 1
fi
if [[ $* == 'load '* && ${FAIL_LOAD:-0} == 1 ]]; then exit 1; fi
if [[ $* == *'itmo-campus-gateway'* && ${FAIL_GATEWAY:-0} == 1 ]]; then exit 1; fi
if [[ " $* " == *' up '* && " $* " == *' bot '* ]]; then
    if [[ $CAMPUS_IMAGE == *:old && ${FAIL_ROLLBACK:-0} == 1 ]]; then exit 1; fi
    if [[ $CAMPUS_IMAGE != *:old && ${FAIL_HEALTH:-0} == 1 ]]; then exit 1; fi
fi
exit 0
''')
        self.command("curl", '''#!/bin/bash
if [[ $* == *'/healthz'* ]]; then exit 0; fi
if [[ $* == *'https://'* && ${FAIL_TLS:-0} == 1 ]]; then exit 1; fi
exit "${FAIL_HTTP:-0}"
''')

    def command(self, name, body):
        path = self.bin / name
        path.write_text(body)
        path.chmod(0o755)

    def old_release(self):
        old = self.root / "releases/old"
        old.mkdir()
        shutil.copyfile(self.release / "compose.production.yaml", old / "compose.production.yaml")
        (old / "image").write_text("itmo-campus:old\n")
        (self.root / "current").symlink_to(old)
        return old

    def run_release(self, **flags):
        env = {**os.environ, "PATH": f"{self.bin}:{os.environ['PATH']}",
               "AVAILABLE_IMAGE": self.image, **flags}
        return subprocess.run(["bash", str(self.release / "release.sh"), self.revision],
                              env=env, capture_output=True, text=True, timeout=15)

    def calls(self):
        return (self.root / "calls").read_text()

    def test_success_promotes_release_and_preserves_data(self):
        marker = self.root / "data/keep"
        marker.write_text("existing database")
        result = self.run_release()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.root / "current").resolve(), self.release)
        self.assertEqual(marker.read_text(), "existing database")
        self.assertIn("--project-name itmo-campus", self.calls())
        self.assertIn("--no-build --pull never --wait", self.calls())

    def test_health_failure_restores_previous_release(self):
        old = self.old_release()
        result = self.run_release(FAIL_HEALTH="1")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Previous release restored", result.stderr)
        self.assertEqual((self.root / "current").resolve(), old)
        self.assertIn("itmo-campus:old compose", self.calls())

    def test_deploy_retry_uses_image_from_original_build_attempt(self):
        retry = self.release.with_name(f"{self.revision}-123-2")
        self.release.rename(retry)
        self.release = retry
        result = self.run_release()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(f"image inspect {self.image}", self.calls())
        self.assertEqual((self.release / "image").read_text().strip(), self.image)
        self.assertEqual((self.root / "current").resolve(), retry)

    def test_missing_image_metadata_fails_before_docker(self):
        (self.release / "image.ref").unlink()
        result = self.run_release()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Image metadata missing", result.stderr)
        self.assertFalse((self.root / "calls").exists())

    def test_image_for_another_commit_is_rejected(self):
        (self.release / "image.ref").write_text(f"itmo-campus:{'b' * 40}-123-1\n")
        result = self.run_release()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("another commit", result.stderr)
        self.assertFalse((self.root / "calls").exists())

    def test_http_failure_also_rolls_back(self):
        old = self.old_release()
        result = self.run_release(FAIL_HTTP="1")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Previous release restored", result.stderr)
        self.assertEqual((self.root / "current").resolve(), old)

    def test_first_failed_release_is_stopped(self):
        result = self.run_release(FAIL_HEALTH="1")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("stop bot", self.calls())
        self.assertFalse((self.root / "current").exists())

    def test_https_application_failure_rolls_back(self):
        self.old_release()
        result = self.run_release(FAIL_TLS="1")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Previous release restored", result.stderr)

    def test_load_failure_does_not_touch_running_service(self):
        old = self.old_release()
        result = self.run_release(FAIL_LOAD="1")
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn(" up ", self.calls())
        self.assertEqual((self.root / "current").resolve(), old)

    def test_gateway_failure_does_not_replace_running_bot(self):
        old = self.old_release()
        result = self.run_release(FAIL_GATEWAY="1")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual((self.root / "current").resolve(), old)
        self.assertNotIn("--wait-timeout 180 bot", self.calls())

    def test_existing_application_secrets_are_preserved(self):
        config = self.root / ".private/.env"
        original = "BOT_TOKEN=123:private-fixture\nOWNER_TELEGRAM_ID=456\n"
        config.write_text(original)
        result = self.run_release()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(config.read_text(), original)

    def test_missing_configuration_fails_before_docker(self):
        (self.root / ".private/.env").unlink()
        result = self.run_release()
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.root / "calls").exists())
        self.assertIn("MINI_APP_URL=https://campus.flacoo.ru", (self.root / ".private/.env").read_text())
        self.assertIn("Fill BOT_TOKEN", result.stderr)

    def test_rollback_failure_is_reported(self):
        self.old_release()
        result = self.run_release(FAIL_HEALTH="1", FAIL_ROLLBACK="1")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("ROLLBACK FAILED", result.stderr)


@unittest.skipUnless(os.name == "posix", "deployment requires Linux")
class SSHDeploymentTests(unittest.TestCase):
    def test_only_three_ssh_secrets_are_required(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            env = {k: v for k, v in os.environ.items() if not k.startswith("SSH_")}
            env.update(PATH=f"{root}:{env['PATH']}", SSH_HOST="192.0.2.1", SSH_USER="root",
                       SSH_PASSWORD="test password '$() !", GITHUB_SHA="a" * 40, GITHUB_RUN_ID="123",
                       CALLS=str(root / "calls"))
            for name, body in {
                "sshpass": '#!/bin/bash\n[[ $1 == -e && -n $SSHPASS ]] || exit 1\nshift\nexec "$@"\n',
                "ssh": '#!/bin/bash\nprintf "%s\\n" "$*" >> "$CALLS"\n',
                "scp": '#!/bin/bash\nprintf "%s\\n" "$*" >> "$CALLS"\n',
            }.items():
                path = root / name
                path.write_text(body)
                path.chmod(0o755)
            script = Path(__file__).resolve().parents[1] / "deploy/ssh-deploy.sh"
            result = subprocess.run(["bash", str(script)], env=env, capture_output=True, text=True, timeout=15)
            self.assertEqual(result.returncode, 0, result.stderr)
            calls = (root / "calls").read_text()
            self.assertIn("StrictHostKeyChecking=accept-new", calls)
            self.assertIn("deploy/compose.gateway.yaml", calls)
            self.assertIn("dist/image.ref", calls)
            self.assertIn("deploy/gateway", calls)
            self.assertNotIn(env["SSH_PASSWORD"], calls + result.stdout + result.stderr)
