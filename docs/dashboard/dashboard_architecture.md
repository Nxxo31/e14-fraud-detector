# FASE 6 — ARQUITECTURA DEL DASHBOARD

## 6.1 Propósito del dashboard

El dashboard es la **interfaz humano-máquina** del sistema E14 Audit Platform. Su objetivo es:

1. Permitir la **supervisión** del estado de procesamiento de actas.
2. Facilitar la **corrección humana** de predicciones de OCR fallidas.
3. Visualizar **métricas forenses y de aprendizaje** en tiempo real.
4. Priorizar **casos críticos** requeridos por el motor de reglas forenses.

### Usuarios objetivo

| Rol | Función en el dashboard |
|---|---|
| **Auditor Electoral** | Revisar actas marcadas como "Revision Humana" y decidir su validez. Corregir números de votos erróneos. |
| **Administrador del Sistema** | Monitorear el flujo de actas, métricas de modelos, y estado del pipeline. |
| **Operador de Datos** | Carga masiva de actas, descarga de reportes, y gestión de casos. |
| **Científico de Datos** | Acceso al dataset histórico, análisis de CER, y disparo de re-entrenamientos. |

---

## 6.2 Arquitectura de vistas (mockup conceptual)

### Vista 1: Cola de Revisión (Prioridad Alta)

**Propósito:** Mostrar únicamente las actas que necesitan atención humana inmediata.

| Columna | Descripción | Acción |
|---|---|---|
| **ID de Acta** | Código DIVIPOLA + consecutivo | Enlace a vista detalle |
| **Departamento** | Geografía | Filtro rápido |
| **Municipio** | Geografía | Filtro rápido |
| **Clasificación** | Sospechoso / Revisión Humana | Color |
| **# Celdas dudosas** | Conteo de predicciones < 90% conf | Contexto de complejidad |
| **Tiempo en cola** | Desde generación | Priorización |
| **Flag** | Manual del usuario | Estado de seguimiento |
| **Acciones** | "Revisar ahora" / "Asignar" / "Descargar imagen" | Interacción |

**Funciomalidad clave:**
- Ordenamiento por urgencia: Actas en "Revisión Humana" primero, luego "Sospechosas".
- Filtros: Por departamento, hora, # de celdas dudosas, y acta específica.
- Acción "Revisar ahora" abre la **Vista 6: Correcciones Humanas**.

### Vista 2: Actas Válidas (Exploración / Auditoría Post-hoc)

**Propósito:** Navegar actas procesadas exitosamente. Útil para auditorías aleatorias y generación de reportes.

| Columna | Descripción |
|---|---|
| **ID Acta** | Identificador único |
| **OCR Completado** | Timestamp de finalización |
| **CER Promedio** | Error estimado por acta |
| **Estado Final** | Válido (automático) |
| **Resultados** | Suma de votos detectados |
| **Acciones** | "Ver detalle" / "Invalidar manualmente" / "Descargar CSV" |

**Funciomalidad clave:**
- Exportación batch a CSV/Excel de todas las actas procesadas.
- Comparación cruzada de votos con actas oficiales (si se tiene listado oficial).
- Búsqueda textu por metadatos.

### Vista 3: Actas Sospechosas (Prioridad Media)

**Propósito:** Actas que pasaron por el motor forense y se hallaron anomalías. No requieren revisión humana obligatoria pero se recomienda.

- Mismos columnas que Vista 2 pero con columnas adicionales:
  - **Regla(s) disparadas** (ej: `R3`, `R7`)
  - **Severidad de la anomalía**
- Función **"Solicar revisión experta"** que permite que un operador la saque de la cola y la eleve a "Revisión Humana".

### Vista 4: Documentos Invalidados (Evidencias)

**Propósito:** Archivar actas clasificadas como Inválidas por el sistema o por un auditor.
- Obligatoriamente incluye el **reporte forense detallado** (`forensic_report.json`).
- Vista de solo lectura para la mayoría de usuarios (no se edita post-invalidez).
- Permite descarga de imagenes y reporte PDF para procesos formales de impugnación.

### Vista 5: Estadísticas Generales (BI)

**Propósito:** Panel gerencial / de sistema. No interactivo (dashboard).

| Métrica | Tipo de visualización | Frecuencia de actualización |
|---|---|---|
| Actas procesadas / hora | Contador numérico grande | Tiempo real |
| Latencia promedio por acta | Gráfico de barras | Tiempo real |
| Distribución clasificaciones | Pastel (gauge) | 30 seg |
| TOP Departamentos con anomalías | Heatmap de Colombia | 5 min |
| CER por modelo (versión) | Línea temporal | Trigger manual |
| Tasa de intervención humana | Progreso (gauge 0-100%) | 5 min |
| Muestras disponibles para re-entren | Contador circular | Tiempo real |
| Historia de versiones de modelo | Tabla con badges | Manual |

### Vista 6: Correcciones Humanas (Misión Crítica)

**Propósito:** Interfaz principal donde el auditor interactúa con la predicción del modelo.

**Diseño propuesto (wireframe):**

```
┌─────────────────────────────────────────────────────────────────────┐
│ ACTA: 01-034-001 │ Mesas: JUN 24 2026 │ Estado: EN REVISIÓN        │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  [Imagen recortada de la CELDA DE VOTO individual]       │         │
│  Mostrando solo la casilla del candidato X            │         │
│                                                                     │
├─────────────────────────────────────────────────────────────────────┤
│  [Imagen puede ser ampliada o en tooltip]           │         │
├─────────────────────────────────────────────────────────────────────┤
│  Predicción TrOCR:  [  3  4  ]  (confianza: 87%)                    │
│  Corregir a:        [  3  4  ]  <--- Input editable por humano      │
│                                                                     │
│  [✓ Correcto      ] [✗ Incorrecto   ] [⏩ Saltar acta]             │
│                                                                     │
│  Comentario (opcional): ________________________________________  │
│                                                                     │
│  [Finalizar Corrección de Celda]                                  │
├─────────────────────────────────────────────────────────────────────┤
│  Progreso de la Acta: Candidato 3 / 8                              │
│  [===========>        ]                                           │
└─────────────────────────────────────────────────────────────────────┘
```

**Funciomalidad clave:**
- **Navegación célula por célula:** El auditor ve una celda a la vez, no la acta completa, para minimizar distracción y maximizar enfoque.
- Doble input: El audidor puede pulsar "Correcto" si la predicción coincide, o editar el número directamente.
- Auto-salto: Al finalizar una celda, automáticamente muestra la siguiente celda de la misma acta.
- **Atajo de teclado:** Teclas numéricas directas, Enter para "Correcto", Esc para "Saltar".

### Vista 7: Evolución del Modelo

**Propósito:** Monitoreo del pipeline de Active Learning.

| Sección | Contenido | Audiencia |
|---|---|---|
| **Dispuestas históricas** | Tabla con cada dataset generado (# muestras, CER prom) | Científico de datos |
| **Compare versiones** | Selector de modelo TrOCR vN vs v(N+1) con CERlado | Científico de datos |
| **Trigger manual** | Botón "Disparar nuevo fine-tuning" con parámetros | Admin |
| **Estado del trigger** | En espera / Entrenando / Completado / Fallo | Admin |
| **Log de entrenamiento** | Consola con salida de comando de training | Técnico |

---

## 6.3 Consideraciones técnicas del frontend

| Aspecto | Decisión arquitectónica | Justificación |
|---|---|---|
| **Framework** | Gradio (Python) o Next.js (React) en primera etapa. | Gradio permite POC rápido con Python. Next.js para producción. |
| **Imagen recortada de celda** | Servicio de back-end genera la imagen PNG dinámica. No se carga la página completa al cliente. | Reducción de ancho de banda y privacidad. |
| **Real-time updates** | WebSockets para que la cola de revisión se actualice sin recargar página. | Flujo de trabajo eficiente. |
| **Multi-dispositivo** | Diseño responsivo mínimo, optimizado para escritorio. | La tarea de corrección de OCR es intrínsecamente visual, requiere pantalla grande. |
| **Historial de acciones** | Log de cada clic y tecla presionada en el dashboard (para auditoría forense). | Traza completa de quién corrigió qué y cuándo. |
| **Accesibilidad (a11y)** | Cumplir WCAG 2.1 AA como mínimo: contraste de colores, teclado navegable. | Los auditores pueden tener limitaciones visuales o preferir uso exclusivo de teclado. |

---

## 6.4 Requisitos no funcionales del dashboard

| Requisito | Objetivo | Nota de riesgo |
|---|---|---|
| **Autenticación** | JWT + roles (Auditor/Admin/Científico) | Sin autenticación anónima para auditoría de votos |
| **Sesión única** | No permitir login simultáneo del mismo usuario | Prevención de colisiones al editar la misma acta |
| **Timeout** | 30 min de inactividad | Seguridad de datos electorales |
| **Auditoría** | Cada acción queda con `revisor_id`, timestamp, IP | Traza legal ante impugnaciones |
| **Modo offline** | No aplicable | Requiere conexión a BD y almacenamiento de imágenes |
| **Multi-idioma** | Español (es-CO) únicamente en MVP | Minimizar complejidad inicial |
| **Tiempos de carga** | < 2 seg para cargar nueva celda de revisión | Crítico para el flujo de correcciones |

---

## 6.5 Alternativas de tecnología descartadas para el dashboard

| Opción | Descarte | Razón |
|---|---|---|
| **Aplicación móvil nativa** | Descartada | Fase MVP no justifica costo. La corrección de OCR es tarea de escritorio. |
| **Interfaz CLI única** | Descartada | Los auditores necesitan ver imágenes, no texto plano. |
| **Streamlit** | Reservada para primera iteración (POC) | Más fácilից de levantar rápidamente que Gradio para tareas simples, pero menos flexible para vistas complejas multi-página. Gradio ya aplicado en otras fases. |
| **Aplicación de escritorio (Electron)** | Descartada | Mayor complejidad de packaging sin beneficio adicional sobre web. El stack web es suficiente. |