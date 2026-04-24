"""
intents/ecb_hawkometer.py
Intent handler for ECB_HAWKOMETER — wires into the main router dispatch system.
"""

import os
import sys

def run(params: dict):
    """Entry point called by router.dispatch() for ECB_HAWKOMETER intent."""
    # Add ecb_hawkometer package to path if needed
    workspace_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if workspace_root not in sys.path:
        sys.path.insert(0, workspace_root)
    
    from ecb_hawkometer.main import run_pipeline
    run_pipeline()
