# Legacy Backend Code

This directory contains FastAPI backend code from a previously discarded webapp approach.

## Status

**Archived Date:** 2025-01-28  
**Status:** Not Used  
**Reason:** Webapp approach was discarded in favor of standalone desktop GUI application

## Contents

- `api/` - FastAPI application code including:
  - `main.py` - FastAPI app with REST/WebSocket endpoints
  - `dbc.py` - DBC file upload/decode router
  - `dbc_store.py` - DBC persistence helpers
  - `metrics.py` - Metrics API endpoint

**Note:** The `backend/api/` directory also contains FastAPI code that is considered legacy and unused. Both locations contain archived code for reference.

## Current Application

The active application is a standalone PySide6 desktop GUI located in `host_gui/`.

The FastAPI backend code in this directory and `backend/api/` is **not used** by the desktop application and is kept **for reference only**.

## Usage

If you need to reference this code:
1. This code may contain useful patterns (e.g., DBC persistence)
2. Do not import or use directly in active code
3. Extract useful patterns to shared location if needed
4. Consider removing this directory if patterns are no longer useful
