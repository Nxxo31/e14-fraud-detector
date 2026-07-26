# E14 Fraud Detector v0.1.0-preprod

## Estado de Producción

| Componente         | Estado | Detalle                              |
|--------------------|--------|--------------------------------------|
| Pipeline E2E         | ✅     | 5/5 actas sin errores                 |
| Verificación de sistema | ✅     | FastAPI, OpenCV, Tesseract, NIM ok  |
| Configuración       | ✅     | .env.example con todos los secrets   |
| Tag/Packaging       | ✅     | v0.1.0-preprod en GitHub               |
| Tests unitarios     | ⏳     | Sprint 1: Agregar tests              |
| Calibración Capa 1  | ⏳     | Sprint 1: Revisar umbrales           |
| Capa 2 VLM NIM      | ⏳     | Sprint 2: Integrar prompts finales     |
| Infra producción    | ⏳     | Sprint 3: Docker + Celery              |
| Dashboard           | ⏳     | Sprint 4: React + API RESTconnected   |

## Veredicto del Pipeline (5 muestras)

| Acta        | Score | Veredicto  |
|-------------|-------|------------|
| Anza.pdf      | 0.29  | LEGITIMA   |
| Turbo_倾心001.pdf | 0.36  | SOSPECHOSA |
| Turbo_002.pdf | 0.37  | SOSPECHOSA |
| Turbo_006.pdf | 0.32  | SOSPECHOSA |
| Turbo_015.pdf | 0.40  | SOSPECHOSA |

**Nota:** Las actas Turbo tienen scores en zona SOSPECHOSA (0.29-0.60).
Necesitamos validar con datos de suelo (ground truth) para calibrar umbrales.

## Scripts de Validación

```bash
# Verificar sistema completo
python3 scripts/validate_pipeline.py

# El resultado se guarda en:
#   data/output/validation_report.json
```

## Repository Status

- URL: https://github.com/Nxxo31/e14-fraud-detector
- Branch: main
- Tag: v0.1.0-preprod
- Commits: 3 (incluyendo consolidación inicial)
