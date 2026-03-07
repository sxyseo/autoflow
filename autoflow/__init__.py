"""
Autoflow - Autonomous AI Development System

An open-source autonomous AI development system that enables AI agents
to independently develop, test, review, and commit code with minimal
human intervention.
"""

__version__ = "0.1.0"
__author__ = "Autoflow Team"

# Core components will be imported here as they are implemented
# from autoflow.core.orchestrator import AutoflowOrchestrator
# from autoflow.core.config import load_config
# from autoflow.core.state import StateManager

# Web dashboard components
from autoflow.web import app as web_app

__all__ = [
    "__version__",
    "web_app",
]
