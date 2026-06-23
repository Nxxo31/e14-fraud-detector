# E14 Audit Platform — Auditoría Ciudadana de Actas E-14 (Colombia)

**Última actualización:** 2026-06-22
**Sprint:** Fases 1-10 implementación completa

## Estado actual

| Fase | Estado | Fecha |
|------|--------|-------|
| F1 — Fundamentos de datos | ✅ Completado | 2026-06-22 |
| F2 — Capa 0 | 🔄 En progreso | |
| F3 — Cola de slots | ⬜ Pendiente | |
| F4 — Capa 1 (OpenCV) | ⬜ Pendiente | |
| F5 — Capa 2 (VLM NIM) | ⬜ Pendiente | |
| F6 — Ingesta ciudadana | ⬜ Pendiente | |
| F7 — Motor comparación | ⬜ Pendiente | |
| F8 — Flujo verificación | ⬜ Pendiente | |
| F9 — Dashboard público | ⬜ Pendiente | |
| F10 — Panel admin | ⬜ Pendiente | |

## Tech Stack (definitivo)

| Capa | Tecnología | Estado |
|---|---|---|
| Base de datos | SQLite (dev) → PostgreSQL (prod) | ✅ SQLite operativo |
| Parser PDF | PyMuPDF (fitz) | ✅ MVP existente |
| QR/Barcode | pyzbar | ⬜ Pendiente |
| Visión (Capa 1) | OpenCV | ⬜ Pendiente |
| VLM (Capa 2) | Hermes Agent + NIM | ⬜ Pendiente |
| Frontend | — | ⬜ Pendiente |
| Dashboard mapa | — | ⬜ Pendiente |

## Datos de muestra

5 PDFs E-14 en `data/pdf_muestra/`:

| Archivo | Mesa | Municipio | Tamaño |
|---------|------|-----------|--------|
| Anza.pdf | 01-034-01-001-000 | Anzá | 47 KB |
| Turbo_015.pdf | 01-280-00-000-015 | Turbo | 59 KB |
| Turbo_001.pdf | 01-280-00-000-001 | Turbo | 56 KB |
| Turbo_002.pdf | 01-280-00-000-002 | Turbo | 60 KB |
| Turbo_006.pdf | 01-280-00-000-006 | Turbo | 57 KB |

## Archivos clave

- `schema_sqlite.sql` — Esquema SQLite adaptado de PostgreSQL
- `data/e14_audit.db` — Base de datos SQLite (5 actas insertadas)
- `data/pdf_muestra/` — 5 PDFs E-14 de muestra
- `create_db.py` — Script para crear la base de datos
- `seed_data.py` — Script para poblar datos de muestra

## Decisiones de diseño

1. **SQLite en lugar de PostgreSQL** — No se pudo instalar PostgreSQL (requiere sudo). Se adaptó el schema con tipos SQLite (INTEGER para booleanos, TEXT para UUIDs y timestamps, REAL para floats). Los triggers de PostgreSQL se simplificaron. Migración a PostgreSQL planificada para producción.

2. **Código de departamento DIVIPOLA** — Antioquia usa código 01 (oficial DIVIPOLA). Anzá = código 034, Turbo = código 280.

3. **Formato mesa_key** — `{depto}-{municipio}-{zona}-{puesto}-{mesa}` con zero-padding de 3 dígitos para municipio y mesa, 2 dígitos para puesto.