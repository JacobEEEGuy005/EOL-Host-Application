"""
Shared regex patterns for oscilloscope command parsing.

This module centralizes all regex patterns used for parsing oscilloscope SCPI commands
across the codebase to avoid duplication and ensure consistency.
"""
import re

# Oscilloscope command parsing patterns
REGEX_ATTN = re.compile(r'ATTN\s+([\d.]+)', re.IGNORECASE)
REGEX_TDIV = re.compile(r'TDIV\s+([+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?)', re.IGNORECASE)
REGEX_VDIV = re.compile(r'VDIV\s+([+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?)', re.IGNORECASE)
REGEX_OFST = re.compile(r'OFST\s+([+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?)', re.IGNORECASE)
REGEX_NUMBER = re.compile(r'([+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?)')
REGEX_NUMBER_SIMPLE = re.compile(r'([\d.]+)')
REGEX_TRA = re.compile(r'TRA\s+(\w+)', re.IGNORECASE)
REGEX_PAVA = re.compile(r'C\d+:PAVA\s+MEAN,([+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?)V?', re.IGNORECASE)

