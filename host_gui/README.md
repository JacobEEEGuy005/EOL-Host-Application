Host GUI (PySide6) prototype

Run locally (recommended inside the project's virtualenv):

```cmd
cd host_gui
python -m pip install -r requirements.txt
python main.py
```

This prototype uses the existing `SimAdapter` from `backend.adapters.sim` and shows a minimal UI to list DBCs, display live frames, and send frames.
