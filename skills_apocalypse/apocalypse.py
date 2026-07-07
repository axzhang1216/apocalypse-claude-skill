#!/usr/bin/env python3
"""Wrapper for apocalypse package"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from apocalypse.__main__ import main

if __name__ == "__main__":
    sys.exit(main())