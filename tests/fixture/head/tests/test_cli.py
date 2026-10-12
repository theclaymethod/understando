import subprocess
import sys
import unittest


class CliTest(unittest.TestCase):
    """The e2e check: it drives the real CLI in a subprocess."""

    def run_cli(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, "-m", "wallet", *args], capture_output=True, text=True)

    def test_an_overdraft_is_refused(self) -> None:
        out = self.run_cli("withdraw", "10", "11")
        self.assertEqual(out.returncode, 3)
        self.assertIn("refused", out.stderr)


if __name__ == "__main__":
    unittest.main()
