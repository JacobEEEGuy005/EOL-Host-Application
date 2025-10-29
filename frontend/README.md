# Frontend

This folder contains a minimal Vite + React frontend for the EOL Host Application.

Run locally:

```cmd
cd frontend
npm install
npm run dev -- --host
```

Then open http://localhost:5173/ (or the Network URL printed by Vite). The backend must be running at http://localhost:8000 for API calls to work.

Contents (planned):
- `frontend/src/` - React/TypeScript source files
- `frontend/public/` - static assets

Development
```bash
cd frontend
npm install
npm run dev
```

Production build
```bash
cd frontend
npm run build
# artifacts in frontend/dist will be served by backend in production
```
