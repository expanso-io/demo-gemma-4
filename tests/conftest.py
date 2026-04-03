"""Shared pytest fixtures and configuration."""

import os
import sys

# Add project root to path so we can import capture_frame if needed
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
