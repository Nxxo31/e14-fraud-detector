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

---

## Estado Operativo

*Actualizado: 2026-07-02 | Fusionado desde CURRENT_TASK.md (archivo obsoleto)*

| Fase | Descripción | Estado | Detalles |
|------|-------------|--------|----------|
| F1 | Base de datos PostgreSQL + Supabase | ✅ Completada | 11 tablas, 2 views, triggers, 5 actas migradas |
| F2 | Capa 0 — validación aritmética | ✅ Completada | 7 discrepancias generadas (excede_total, no_coincide, nivelacion, firmas) |
| F3 | Cola de slots + workers concurrentes | ✅ Completada | Worker pool paralelo validado, 0 colisiones |
| F4 | Capa 1 — visión por computador (OpenCV) | ✅ Completada | 3 scores implementados: grosor, separador, tinta. 30 discrepancias tipo 'trazo_anomalo' detectadas |
| F5 | Capa 2 — VLM dirigido (NVIDIA NIM) | ⬜ Pendiente | Ejecuta prompts sobre celdas con score_capa1 > 0.6 |
| F6 | Ingesta de evidencia ciudadana | ⬜ Pendiente | Endpoint para subir fotos + Capa 1/2 |
| F7 | Motor comparación oficial vs ciudadano | ⬜ Pendiente | Generar discrepancias de tipo 'discrepancia_oficial_vs_ciudadano' |
| F8 | Flujo de verificación ciudadana (consenso) | ⬜ Pendiente | Endpoint votos + trigger consenso |
| F9 | Dashboard público (3 vistas) | ⬜ Pendiente | Mapa, mesas legítimas, cola verificación |
| F10 | Panel admin + exportación impugnaciones | ⬜ Pendiente | Vista admin + PDF exportable |

## Supabase conectado

- **Project:** `oawxinjygprnftkgcjyr` (E-14)
- **11 tablas + 2 views**
- **5 actas migradas**
- **37 discrepancias totales:**
  - Capa 0 (aritmética): 7 (excede_total, no_coincide, nivelacion, firmas)
  - Capa 1 (visión): 30 (trazo_anomalo)

## Resultados Capa 1 (OpenCV)

Scores por acta (votos_candidato_1):
- Anza (clean): 0.58 ✅
- Turbo 015 (controversial): 0.70 ⚠️
- Turbo 001 (nivelación+faltan firmas): 0.70 ⚠️
- Turbo 002 (trazo_grueso reportado): 0.70 ⚠️
- Turbo 006 (clean): 0.70 ⚠️

**Limitación conocida:** Las coordenadas de celdas son aproximadas y generan scores de alto nivel incluso en actas limpias. Necesita calibración manual para confirmar precisión real.

## Bloqueo: Calibración visual necesaria

Para avanzar a Fase 5 (VLM NIM) necesitamos calibrar las coordenadas exactas de las celdas de votación para cada PDF de muestra, o aceptar que los scores de Capa 1 actúan como señal de dirección (tendencia) más que como verdad absoluta.

## Tokens Supabase (guardados en memoria segura)


## Archivos clave creados/modificados

- `schema_postgresql.sql` — Schema completo (11 tablas + views + triggers)
- `migrate_data_supabase.py` — Migración SQLite → Supabase
- `generate_discrepancias_supabase.py` — Generación de discrepancias Capa 0
- `fase4/capa1_opencv.py` — Pipeline de visión por computador con OpenCV
- `SUPABASE_SETUP.md` — Guía de configuración Supabase

---

*Nota: Para actualizar estado operativo, editar esta sección de PROJECT.md directamente.*
