# CURRENT_TASK.md — E14 Audit Platform

**Fecha:** 2026-06-22
**Sprint:** Fases 1-4 completadas, Fases 5-10 en espera

## Estado de avance

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
