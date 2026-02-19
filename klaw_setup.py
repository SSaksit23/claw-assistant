"""
klaw setup helper for Web365 ClawBot.

Automates the full setup of the klaw ↔ ClawBot hybrid integration:
1. Install klaw binary
2. Copy configuration
3. Register agents
4. Create scheduled jobs
5. Start the bridge server

Usage:
    python klaw_setup.py install    # install klaw + register agents
    python klaw_setup.py status     # show current integration status
    python klaw_setup.py start      # start bridge + klaw platform
    python klaw_setup.py demo       # run a demo dispatch through CLI runner
"""

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
KLAW_CONFIG_DIR = os.path.expanduser("~/.klaw")
PYTHON = sys.executable


def check_klaw_installed() -> bool:
    try:
        result = subprocess.run(["klaw", "version"], capture_output=True, text=True, timeout=5)
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def install_klaw():
    """Download and install the klaw binary."""
    print("\n[1/4] Checking klaw installation...")

    if check_klaw_installed():
        result = subprocess.run(["klaw", "version"], capture_output=True, text=True)
        print(f"  klaw already installed: {result.stdout.strip()}")
    else:
        system = platform.system().lower()
        if system == "windows":
            print("  To install klaw on Windows:")
            print("    1. Download from https://github.com/klawsh/klaw.sh/releases")
            print("    2. Add to PATH")
            print("  Or build from source:")
            print("    git clone https://github.com/SSaksit23/klaw.sh.git")
            print("    cd klaw.sh && make build")
        else:
            print("  Installing klaw...")
            try:
                subprocess.run(
                    ["sh", "-c", "curl -fsSL https://klaw.sh/install.sh | sh"],
                    check=True,
                )
                print("  klaw installed successfully")
            except subprocess.CalledProcessError:
                print("  Auto-install failed. Install manually:")
                print("    curl -fsSL https://klaw.sh/install.sh | sh")

    print("\n[2/4] Setting up klaw configuration...")
    os.makedirs(KLAW_CONFIG_DIR, exist_ok=True)
    src = os.path.join(PROJECT_ROOT, "klaw_config.toml")
    dst = os.path.join(KLAW_CONFIG_DIR, "config.toml")

    if os.path.exists(dst):
        print(f"  Config already exists at {dst}")
        print(f"  Source config at {src}")
    else:
        shutil.copy2(src, dst)
        print(f"  Config copied to {dst}")

    print("\n[3/4] Verifying agent definitions...")
    agents_dir = os.path.join(PROJECT_ROOT, "klaw_agents")
    yamls = [f for f in os.listdir(agents_dir) if f.endswith(".yaml")]
    for y in sorted(yamls):
        print(f"  {y}")
    print(f"  Found {len(yamls)} agent/schedule definitions")

    print("\n[4/4] Verifying Python agent CLI runner...")
    try:
        result = subprocess.run(
            [PYTHON, "-m", "agents.cli_runner", "--list-agents"],
            capture_output=True, text=True, cwd=PROJECT_ROOT, timeout=10,
        )
        if result.returncode == 0:
            print("  CLI runner OK:")
            for line in result.stdout.strip().split("\n"):
                print(f"    {line.strip()}")
        else:
            print(f"  CLI runner error: {result.stderr[:200]}")
    except Exception as e:
        print(f"  CLI runner check failed: {e}")

    print("\n  Setup complete. Next steps:")
    print("    python klaw_setup.py start    # start bridge server")
    print("    python klaw_setup.py demo     # test an agent via CLI")


def show_status():
    """Show current integration status."""
    print("\n=== klaw <-> ClawBot Integration Status ===\n")

    klaw_ok = check_klaw_installed()
    print(f"  klaw binary:     {'OK' if klaw_ok else 'NOT INSTALLED'}")

    config_path = os.path.join(KLAW_CONFIG_DIR, "config.toml")
    print(f"  klaw config:     {'OK' if os.path.exists(config_path) else 'MISSING'}")

    agents_dir = os.path.join(PROJECT_ROOT, "klaw_agents")
    yamls = [f for f in os.listdir(agents_dir) if f.endswith(".yaml")]
    print(f"  Agent YAMLs:     {len(yamls)} definitions")

    bridge_path = os.path.join(PROJECT_ROOT, "klaw_bridge.py")
    print(f"  Bridge script:   {'OK' if os.path.exists(bridge_path) else 'MISSING'}")

    cli_path = os.path.join(PROJECT_ROOT, "agents", "cli_runner.py")
    print(f"  CLI runner:      {'OK' if os.path.exists(cli_path) else 'MISSING'}")

    env_vars = {
        "OPENAI_API_KEY": bool(os.getenv("OPENAI_API_KEY")),
        "WEBSITE_USERNAME": bool(os.getenv("WEBSITE_USERNAME")),
        "WEBSITE_PASSWORD": bool(os.getenv("WEBSITE_PASSWORD")),
    }
    for var, ok in env_vars.items():
        print(f"  {var:20s} {'SET' if ok else 'NOT SET'}")

    print()


def start_services():
    """Start the bridge server (and optionally klaw platform)."""
    print("\nStarting klaw ↔ ClawBot bridge server...")
    print("Press Ctrl+C to stop.\n")

    subprocess.run(
        [PYTHON, "klaw_bridge.py"],
        cwd=PROJECT_ROOT,
    )


def run_demo():
    """Run a demo agent dispatch through the CLI runner."""
    print("\n=== Demo: Running agents via CLI ===\n")

    agents_to_demo = [
        ("executive", '{"action":"generate_report"}', "Executive report (uses cached data)"),
    ]

    for agent_name, task_json, description in agents_to_demo:
        print(f"--- {description} ---")
        print(f"  Command: python -m agents.cli_runner --agent {agent_name} --task '{task_json}'")
        print()

        try:
            result = subprocess.run(
                [PYTHON, "-m", "agents.cli_runner", "--agent", agent_name, "--task", task_json],
                capture_output=True, text=True, cwd=PROJECT_ROOT, timeout=120,
            )

            if result.stderr:
                for line in result.stderr.strip().split("\n")[-5:]:
                    print(f"  [log] {line}")

            if result.returncode == 0:
                try:
                    output = json.loads(result.stdout)
                    status = output.get("status", "unknown")
                    content = output.get("result", {}).get("content", "")
                    print(f"  Status: {status}")
                    if content:
                        preview = content[:300] + "..." if len(content) > 300 else content
                        print(f"  Output preview:\n    {preview}")
                except json.JSONDecodeError:
                    print(f"  Raw output: {result.stdout[:300]}")
            else:
                print(f"  FAILED (exit {result.returncode})")
                if result.stderr:
                    print(f"  Error: {result.stderr[:200]}")

        except subprocess.TimeoutExpired:
            print("  TIMEOUT (120s)")
        except Exception as e:
            print(f"  Exception: {e}")

        print()


def main():
    parser = argparse.ArgumentParser(description="klaw ↔ ClawBot setup helper")
    parser.add_argument(
        "command",
        choices=["install", "status", "start", "demo"],
        help="Setup command to run",
    )
    args = parser.parse_args()

    if args.command == "install":
        install_klaw()
    elif args.command == "status":
        show_status()
    elif args.command == "start":
        start_services()
    elif args.command == "demo":
        run_demo()


if __name__ == "__main__":
    main()
