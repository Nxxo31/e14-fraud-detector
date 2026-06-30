# E14 AUDIT PLATFORM — Arquitectura de Agentes V2

**Diseñado para:** Escalabilidad, explicabilidad, y procesamiento selectivo con VLM.
**Principio rector:** Descomponer el problema para dominarlo. Ningún agente maestro hace todo.

---

## 1. Diagrama de Agentes (simplificado)

```
                     ┌─────────────────────────────────┐
                     │         SUPERVISOR            │
                     │   (orquestación + healthcheck)│
                     └──────────────┬────────────────┘
                                    │
        ┌───────────────────────────┼───────────────────────────┐
        │                           │                           │
 ┌──────▼──────┐        ┌───────────▼────────┐        ┌─────────▼────────┐
 │  Agente     │        │  Agente            │        │   Agente         │
 │  Metadatos  │        │  Segmentación      │        │   QR             │
 └──────┬──────┘        └───────────┬────────┘        └─────────┬────────┘
        │                           │                           │
        └───────────────────────────┬───────────────────────────┘
                                    │
                                    ▼
                     ┌──────────────────────────────────┐
                     │         Agente OCR               │
                     │   (specialized per field type)   │
                     └────────────────┬───────────────┘
                                      │
                                      ▼
                     ┌──────────────────────────────────┐
                     │      Agente Forense              │
                     │   (reglas + anomalías)           │
                     └────────────────┬───────────────┘
                                        │
              ┌─────────────────────────┼─────────────────────────┐
              │                         │                         │
    ┌─────────▼─────────┐    ┌──────────▼──────────┐    ┌──────────▼──────────┐
    │ Agente Estadístico│    │  Agente VLM         │    │  Agente Revisión   │
    │   (scoring)       │    │  (selectivo)        │    │  Humana            │
    └────────────┬──────┘    └─────────────────────┘    └─────────────────────┘
                 │
                 ▼
    ┌──────────────────────────────────┐
    │       Agente Aprendizaje          │
    │   (feedback loop + retrain)      │
    └──────────────────────────────────┘
```

---

## 2. Detalle por Agente

### 2.1 Agente Supervisor

**Responsabilidad única:** Coordinar el flujo de procesamiento de un documento E-14 desde su recepción hasta su clasificación final.

**Interface:**
```python
class SupervisorAgent:
    def process_document(self, document_id: str) -> ProcessingResult:
        # 1. Estado inicial = PENDIENTE
        # 2. Llama a cada sub-agente en orden secuencial o paralelo según dependencias
        # 3. Gestiona reintentos (max 3)
        # 4. Persiste estado en DB tras cada fase
        # 5. Si un agente falla, marca ERROR y notifica
```

**Decisiones que toma:**
- Qué agentes ejecutar en paralelo vs. serie.
- Cuándo enviar un caso a VLM (basado en scores de confianza).
- Cuándo solicitar revisión humana.
- Cuándo descartar un documento como "inválido técnico".

---

### 2.2 Agente Metadatos

**Responsabilidad única:** Extraer del PDF todos los datos **impresos** que identifican la acta.

**Inputs:** PDF renderizado a imagen (pagina 1).
**Outputs:**
```json
{
  "departamento": "01",
  "municipio": "280",
  "zona": "01",
  "puesto": "0001",
  "mesa": "001",
  "codigo_mesa": "01-280-01-0001-001",
  "tipo_ejemplar": "transmision",
  "version_formato": "Ver: 01",
  "confianza": 0.98
}
```

**Tecnología:** Tesseract OCR (modo línea) + reglas de validación (regex para códigos DIVIPOLA).
**Validación cruzada:** Sumar 1 departamento + 2 municipio ≠ código mesa → discrepancia metadata.

---

### 2.3 Agente QR

**Responsabilidad única:** Extraer y validar el código QR de la acta.

**Inputs:** PDF página 1 (o imagen de la página 1).
**Outputs:**
```json
{
  "qr_raw_value": "https://www.registraduria.gov.co/...",
  "qr_decodificado": {"depto": "01", "municipio": "280", ...},
  "qr_metadata_match": true,
  "confianza_lectura": 0.95
}
```

**Tecnología:** pyzbar (requiere libzbar-dev).
**Acción si falla:** Marca flag `flag_qr_metadata_mismatch` y pasa a validación manual opcional.

---

### 2.4 Agente Segmentación

**Responsabilidad única:** Localizar con precisión las regiones relevantes del E-14: celdas de votos, zona de firmas, y metadatos.

**Inputs:** Imagen de la página (1 o 2).
**Outputs:**
```json
{
  "celdas_votos": [
    {"tipo": "candidato_1", "bbox_norm": [0.51, 0.32, 0.15, 0.05], "pagina": 1},
    {"tipo": "candidato_2", "bbox_norm": [0.51, 0.40, 0.15, 0.05], "pagina": 1},
    {"tipo": "votos_blanco", "bbox_norm": [0.55, 0.65, 0.12, 0.04], "pagina": 2},
    ...
  ],
  "zona_firmas": {"bbox_norm": [0.05, 0.75, 0.90, 0.20], "pagina": 2},
  "zona_metadatos": {"bbox_norm": [0.05, 0.05, 0.40, 0.20], "pagina": 1}
}
```

**Nota crítica:** Las coordenadas son **normalizadas (0-1)** para ser independientes de la resolución y el tamaño del documento.

**Tecnología ideal:** Modelo fine-tuned YOLOv8 o LayoutLM entrenado con ~500 anotaciones de celdas E-14. Mientras, heurísticas OpenCV mejoradas con reglas de layout general del formulario.
**Fallback:** Si el agente no confía (<0.85), envía imagen completa a VLM con prompt de localización.

---

### 2.5 Agente OCR (Hybrid Engine)

**Responsabilidad única:** Leer números dentro de las celdas de votación y texto en los metadatos.

**Doble estrategia:**

#### Para metadatos (texto impreso):
- **Motor:** Tesseract (configurado en modo página).
- **Post-proceso:** Limpieza, regex, validación contra catalogo DIVIPOLA.

#### Para celdas de votos (manuscrito):
- **Motor principal:** TrOCR fine-tuned con celdas E-14.
- **Motor de contingencia:** VLM prompt directo sobre la celda si TrOCR confía <0.90.

**Outputs por celda:**
```json
{
  "celda": "votos_candidato_1",
  "valor": 142,
  "texto_raw": "142",
  "confianza": 0.97,
  "metodo": "trocr_finetuned",
  "alternativas": [
    {"valor": "142", "confianza": 0.97},
    {"valor": "152", "confianza": 0.15}
  ]
}
```

---

### 2.6 Agente Forense (Forensic Engine)

**Responsabilidad única:** Aplicar reglas de consistencia y detectar anomalías estructurales sin usar ML.

**Reglas Hard-coded (no negociables):**
1. Suma de votos candidatos + blanco + nulos + no marcados = total votos urna.
2. Total votos urna ≤ total votantes E11 +15% (margen embarque).
3. Total votos incinerados ≤ total votos urna.
4. Recuento firmas página 2 >= 3 (mínimo legal) para kept simple calculation
5. Cantidad numeros en celdas; total digit extraction valid equals what was extracted or not.
 extracted figures match what we got sum of.
 all we got for each one.
 simple addition.
 total resulting plus sum total compared expected what.

 figures match from airdrop chosen6. full what happens if there a marked deleted or else alteration in digit result by OpenCV not found yes in reading dataextracted figures again after will OCR check.

 figures got plus finally what counted key ones use.
 simple yes count figures up and verify.
 actual real count repeated matches.
8 each what page should have fields marked count total expected from document level.
.
 missing anything a seen reading terms reading actual what if yes will repeat.
 figures verify some if in actual valid form with all fields present.
 any find given level.
 figures plus holes noted and use.
 valid figures use sum terms.
 say forms missing yes actual figures valid or what term.

__OUTPUTS__
- very complex writing multi-layered cross-referencing.
 embed this inoutput a given listing.
```json
[
  {"type": "arithmetic_inconst", "severity": "CRITICAL", "score": 1, "desc": "Total invalid"}.
  some real writing here valid check figures. where. sum them all plus verify count listed terms total.
- recharge. in expected above all if figures, put in them missing.
 matching a total above a margin total sum. beyond what percent valid used target.
 if beyond yes plus match total. total, valid figure out exact amount error.
 if total wrong beyond certain valid.
. where actual such target. then give reason.
 harder .push figures what expected list. with valid. and terms as found