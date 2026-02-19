"""Allow running agents as a module: python -m agents --agent <name> --task '{...}'"""
from agents.cli_runner import main

if __name__ == "__main__":
    main()
