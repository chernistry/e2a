#!/usr/bin/env python3
"""
CLI entry point for processing stage management.
Usage: python cli_stages.py [command] [options]
"""

import sys
import os

# Add the app directory to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'app'))

from app.cli.processing_stages import processing_stages

if __name__ == '__main__':
    processing_stages()
