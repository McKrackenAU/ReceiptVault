from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[2]
DEPLOY = ROOT / "deploy"


def _bash_n(script: Path) -> None:
    result = subprocess.run(["bash", "-n", str(script)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_systemd_uses_run_api_script():
    api = (DEPLOY / "systemd/receiptvault.service").read_text()
    worker = (DEPLOY / "systemd/receiptvault-worker.service").read_text()
    assert "ExecStart=/opt/receiptvault/deploy/run-api.sh" in api
    assert "/opt/receiptvault/backend/.venv/bin/dramatiq" in worker
    assert "127.0.0.1 --port 8473" not in api
    http80 = (DEPLOY / "systemd/receiptvault-http80.service").read_text()
    assert "ExecStart=/opt/receiptvault/deploy/lan-http80.sh" in http80


def test_installer_shell_syntax():
    _bash_n(DEPLOY / "install-receiptvault.sh")
    _bash_n(DEPLOY / "repair-in-place.sh")
    _bash_n(DEPLOY / "make-reachable.sh")
    _bash_n(DEPLOY / "run-api.sh")
    _bash_n(DEPLOY / "fix-from-host.sh")
    _bash_n(DEPLOY / "ensure-db.sh")
    _bash_n(DEPLOY / "lan-http80.sh")


def test_bootstrap_and_network_scripts_syntax():
    _bash_n(DEPLOY / "lxc-bootstrap.sh")
    _bash_n(DEPLOY / "guest-network.sh")
    _bash_n(DEPLOY / "lib-network.sh")


def _fn(expr: str) -> str:
    result = subprocess.run(
        ["bash", "-lc", f"source {DEPLOY / 'lib-network.sh'}; {expr}"],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def test_normalize_ipv4_adds_slash24():
    assert _fn('normalize_ipv4_cidr 192.168.13.13') == "192.168.13.13/24"


def test_normalize_uses_slash16_when_router_is_on_another_octet():
    assert _fn('normalize_ipv4_cidr 192.168.13.13 192.168.1.1') == "192.168.13.13/16"


def test_normalize_ipv4_keeps_prefix():
    assert _fn('normalize_ipv4_cidr 192.168.14.13/24') == "192.168.14.13/24"


def test_normalize_strips_url_and_port():
    assert _fn('normalize_ipv4_cidr http://192.168.14.13:8080') == "192.168.14.13/24"


def test_public_url_omits_port_80():
    assert _fn('public_url_for 192.168.14.13 80') == "http://192.168.14.13"
    assert _fn('public_url_for 192.168.14.13 8080') == "http://192.168.14.13:8080"


def test_suggest_static_keeps_octet_on_host_subnet():
    assert _fn('suggest_static_cidr 192.168.14.1/24 13') == "192.168.14.13/24"


def test_cidr_contains_same_subnet_only():
    ok = subprocess.run(
        ["bash", "-lc", f"source {DEPLOY / 'lib-network.sh'}; cidr_contains_address 192.168.14.1/24 192.168.14.13"],
        capture_output=True,
        text=True,
    )
    bad = subprocess.run(
        ["bash", "-lc", f"source {DEPLOY / 'lib-network.sh'}; cidr_contains_address 192.168.14.1/24 192.168.13.13"],
        capture_output=True,
        text=True,
    )
    assert ok.returncode == 0
    assert bad.returncode == 1
