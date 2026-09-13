from pathlib import Path
import subprocess


def test_installer_shell_syntax():
    script = Path(__file__).resolve().parents[2] / "deploy" / "install-receiptvault.sh"
    result = subprocess.run(["bash", "-n", str(script)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
