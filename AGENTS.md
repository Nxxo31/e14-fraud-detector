# e14-audit-platform — Contexto del agente

## Proyecto
Prototipo de auditoría ciudadana de actas electorales E-14 de Colombia.
Procesa PDFs de muestra (5-18 actas). Repo de escala: e14-auditoria (122k actas).

## Stack
- Python 3.14 + venv en ./venv/
- Framework: FastAPI + uvicorn (puerto 8700)
- Análisis: PyMuPDF + OpenCV + Tesseract + NVIDIA NIM VLM
- DB: SQLite (local) + Supabase PostgreSQL (producción)
- Arquitectura: MVC — engine/ (MODEL) / api/ (CONTROLLER) / dashboard/ (VIEW)

## Development loop for this project

1. Read PROJECT.md → check active phase and known limitations
2. `git status` → ver estado del repo
3. Verificar LSP activo: `hermes lsp status` — si no hay clientes: `hermes lsp restart`
   **Nota en WSL**: El servidor LSP de TypeScript está instalado, pero el cliente solo se conecta cuando un editor (VS Code, etc.) abre un archivo `.ts` o `.tsx`. Mientras no haya un archivo abierto, `hermes lsp status` mostrará `active clients: none`; esto es esperado y no indica un problema. La fuente de verdad para tipos es `mcp__lsp_intelligence__live_diagnostics`, que debe dar 0 errores antes de hacer commit.
4. Skills loaded automatically by the agent before writing code: based on the project's stack (e.g., for Electron projects: electron-desktop-dev; for Next.js: nextjs-best-practices; for Go: go-environment-setup, etc.). The agent loads the appropriate stack-specific skills without needing a file reminder.
5. For tasks >1 archivo or UI work: the agent thinks first about what it's going to build, shows mockups if UI, and only then writes code. No intermediate .md files — design lives inline in PROJECT.md if needed.
6. **LSP gate**: `mcp__lsp_intelligence__live_diagnostics` en archivos modificados — 0 errores
7. **Code review gate**: `delegate_task` con skill `code-review-and-quality` — todos los findings addressados
8. **Secret scan gate**: run `gitleaks detect --staged` (via terminal tool) — no secrets detected
9. Update PROJECT.md with results BEFORE commit (only project doc allowed)
10. **Commit gate**: use GitHub MCP tools to create a commit with conventional message (type(scope): description) and push to the current branch.
11. Next task immediately.

NO vitest, NO jest, NO playwright, NO `tsc --noEmit` directo. Los gates son determinísticos: LSP live_diagnostics + delegate_task review + gitleaks + GitHub commit.
NO separate spec files, drift reports, docs/specs/, architecture overviews, or any .md outside PROJECT.md. Everything goes in PROJECT.md.

## Comandos
- API: `./venv/bin/python api/main.py`
- Pipeline CLI: `./venv/bin/python engine/pipeline.py data/pdf_muestra/Anza.pdf`
- Instalar deps: `./venv/bin/pip install PyMuPDF opencv-python-headless numpy fastapi uvicorn`

## Estado actual (2026-06-26)
- ✅ F1-F4 completadas (DB, aritmética, workers, OpenCV)
- ✅ Capa 2 VLM integrada (llama-3.2-90b-vision via NVIDIA NIM)
- ✅ Batch processing (18 muestras, 0 errores)
- ⬜ F5+ pendientes (ingesta ciudadana, comparación, dashboard público)

## Reglas críticas
- Coordenadas normalizadas (0-1) SIEMPRE — coordenadas fijas en píxeles RECHAZADAS
- Capa 1 (OpenCV) analiza SOLO firmas — nunca números ni texto
- NVIDIA NIM: 3 API keys rotadas, límite ~37 req/min
- Credenciales Supabase SOLO en variables de entorno — nunca en archivos .md

## Loop de trabajo
1. `cat PROJECT.md` → verificar fase activa
2. Activar venv: `source venv/bin/activate`
3. Commit atómico en español → push inmediato
