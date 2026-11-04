"""Compatibility launcher; see docs/TEAM_WORKFLOWS.md for explicit inputs."""
from src.events.legacy import launch

# Importing this file never starts research, reads data or contacts services.
if __name__ == '__main__':
    raise SystemExit(launch('vix', '2021_2025'))
