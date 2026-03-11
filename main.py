"""
main.py — Entry point. Accepts a natural language query via CLI or stdin.

Usage:
    python main.py "Where is Eurozone inflation now?"
    python main.py "Show me the German Bund curve"
    python main.py "Debt-to-GDP across all EU member states"
"""

import sys
import os

# Ensure project root is on the path
sys.path.insert(0, os.path.dirname(__file__))

from router import dispatch

if __name__ == "__main__":
    query = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else input("Query: ")
    dispatch(query)
