-- =====================================================================
-- schema_sqlite.sql — Auditoría Ciudadana de Actas E-14 (SQLite)
-- Adaptación temporal desde PostgreSQL para desarrollo local
-- =====================================================================

-- Extensiones simuladas (SQLite tiene funciones básicas incluidas)
-- No se necesita CREATE EXTENSION en SQLite

-- ---------------------------------------------------------------------
-- Tabla de referencia: divipola (departamentos y municipios)
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS divipole_departamento (
    codigo_departamento TEXT PRIMARY KEY,   -- ej '01'
    nombre_departamento TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS divipole_municipio (
    codigo_departamento TEXT NOT NULL REFERENCES divipole_departamento(codigo_departamento),
    codigo_municipio TEXT NOT NULL,         -- ej '280'
    nombre_municipio TEXT NOT NULL,
    PRIMARY KEY (codigo_departamento, codigo_municipio)
);

-- ---------------------------------------------------------------------
-- actas_oficiales: una fila por documento E-14 oficial descargado
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS actas_oficiales (
    id TEXT PRIMARY KEY,  -- UUID como TEXT (SQLite no tiene UUID nativo)

    -- Identificación de mesa (clave compuesta de negocio)
    mesa_key TEXT NOT NULL,                  -- formato: depto-municipio-zona-puesto-mesa
    codigo_departamento TEXT NOT NULL,
    codigo_municipio TEXT NOT NULL,
    zona TEXT,
    puesto TEXT,
    mesa TEXT NOT NULL,
    lugar_votacion TEXT,

    tipo_ejemplar TEXT NOT NULL CHECK (tipo_ejemplar IN ('delegados','claveros','transmision')),

    -- Origen del documento
    pdf_url TEXT,
    pdf_storage_path TEXT,                   -- ruta en object storage si se re-almacena
    kit_numero TEXT,
    formulario_numero TEXT,
    version_formato TEXT,                    -- ej 'Ver: 01'

    -- QR / barcode
    qr_raw_value TEXT,
    qr_decoded_match INTEGER,                 -- 0/1 (SQLite no tiene BOOLEAN)

    -- Estructura documental
    paginas_total INTEGER,
    paginas_esperadas INTEGER DEFAULT 2,
    pagina_2_vacia INTEGER,                   -- 0/1
    firmas_detectadas INTEGER,

    -- Datos de nivelación de mesa
    total_votantes_e11 INTEGER,
    total_votos_urna INTEGER,
    total_votos_incinerados INTEGER,

    -- Votación
    votos_candidato_1 INTEGER,
    votos_candidato_2 INTEGER,
    votos_blanco INTEGER,
    votos_nulos INTEGER,
    votos_no_marcados INTEGER,
    suma_total_calculada INTEGER,             -- calculado por el sistema, no el impreso

    -- Resultado de validaciones de Capa 0
    flag_aritmetica_excede_total INTEGER DEFAULT 0,
    flag_aritmetica_no_coincide INTEGER DEFAULT 0,
    flag_nivelacion_inconsistente INTEGER DEFAULT 0,
    flag_paginas_incompletas INTEGER DEFAULT 0,
    flag_firmas_insuficientes INTEGER DEFAULT 0,
    flag_qr_metadata_mismatch INTEGER DEFAULT 0,

    -- Procesamiento
    capa_maxima_procesada INTEGER DEFAULT 0,      -- 0, 1 o 2
    estado_procesamiento TEXT DEFAULT 'pendiente'
        CHECK (estado_procesamiento IN ('pendiente','procesando','completado','error')),

    creado_en TEXT DEFAULT (datetime('now')),
    actualizado_en TEXT DEFAULT (datetime('now')),

    UNIQUE (mesa_key, tipo_ejemplar)
);

CREATE INDEX IF NOT EXISTS idx_actas_mesa_key ON actas_oficiales (mesa_key);
CREATE INDEX IF NOT EXISTS idx_actas_departamento ON actas_oficiales (codigo_departamento);
CREATE INDEX IF NOT EXISTS idx_actas_estado_proc ON actas_oficiales (estado_procesamiento);
CREATE INDEX IF NOT EXISTS idx_actas_flags ON actas_oficiales (flag_aritmetica_excede_total, flag_aritmetica_no_coincide);

-- ---------------------------------------------------------------------
-- evidencia_ciudadana: fotos/escaneos aportados por ciudadanos
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS evidencia_ciudadana (
    id TEXT PRIMARY KEY,  -- UUID como TEXT

    mesa_key TEXT NOT NULL,
    imagen_url TEXT NOT NULL,
    imagen_storage_path TEXT,

    aportante_id TEXT,                        -- referencia a usuario si está autenticado
    aportante_ip_hash TEXT,                   -- hash, nunca IP en crudo

    -- Extracción automática (reutiliza Capa 1/2)
    votos_extraidos TEXT,                     -- JSON como TEXT
    metodo_extraccion TEXT CHECK (metodo_extraccion IN ('manual','ocr_zona','vlm','mixto')),
    confianza_extraccion REAL,                -- 0.000 a 1.000

    estado_revision TEXT DEFAULT 'pendiente'
        CHECK (estado_revision IN ('pendiente','procesada','rechazada_calidad')),

    creado_en TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_evidencia_mesa_key ON evidencia_ciudadana (mesa_key);
CREATE INDEX IF NOT EXISTS idx_evidencia_estado ON evidencia_ciudadana (estado_revision);

-- ---------------------------------------------------------------------
-- cola_procesamiento: "slots" para procesamiento concurrente seguro
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS cola_procesamiento (
    id TEXT PRIMARY KEY,  -- UUID como TEXT
    mesa_key TEXT NOT NULL,
    acta_id TEXT REFERENCES actas_oficiales(id),

    capa_actual INTEGER NOT NULL DEFAULT 0 CHECK (capa_actual IN (0,1,2)),
    estado_slot TEXT NOT NULL DEFAULT 'pendiente'
        CHECK (estado_slot IN ('pendiente','tomado','procesando','completado','error')),

    worker_id TEXT,                           -- identificador del sub-agente que tomó el slot
    intentos INTEGER DEFAULT 0,
    max_intentos INTEGER DEFAULT 3,
    ultimo_error TEXT,

    tomado_en TEXT,
    completado_en TEXT,
    creado_en TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_cola_estado_capa ON cola_procesamiento (estado_slot, capa_actual);
CREATE INDEX IF NOT EXISTS idx_cola_mesa_key ON cola_procesamiento (mesa_key);

-- ---------------------------------------------------------------------
-- discrepancias: anomalías detectadas (oficial vs ciudadano, o internas)
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS discrepancias (
    id TEXT PRIMARY KEY,  -- UUID como TEXT

    mesa_key TEXT NOT NULL,
    acta_oficial_id TEXT REFERENCES actas_oficiales(id),
    evidencia_ciudadana_id TEXT REFERENCES evidencia_ciudadana(id),

    campo_afectado TEXT NOT NULL,             -- ej 'votos_candidato_1', 'total_urna'
    valor_oficial TEXT,
    valor_ciudadano TEXT,

    tipo_anomalia TEXT NOT NULL CHECK (tipo_anomalia IN (
        'aritmetica_excede_total',
        'aritmetica_no_coincide',
        'nivelacion_inconsistente',
        'paginas_incompletas',
        'firmas_insuficientes',
        'qr_metadata_mismatch',
        'trazo_anomalo',
        'separador_anomalo',
        'tachon_sobreescritura',
        'discrepancia_oficial_vs_ciudadano',
        'otro'
    )),

    -- Scores por capa (NULL si esa capa no se ejecutó)
    score_capa0 REAL,
    score_capa1 REAL,
    score_capa2 REAL,

    razon_flag TEXT,                          -- explicación legible generada por el sistema
    evidencia_imagen_recorte_url TEXT,         -- recorte de la celda específica

    prioridad TEXT DEFAULT 'media' CHECK (prioridad IN ('baja','media','alta')),

    estado TEXT NOT NULL DEFAULT 'por_verificar'
        CHECK (estado IN ('por_verificar','verificado_legitimo','verificado_anomalo')),

    votos_confirma INTEGER DEFAULT 0,
    votos_rechaza INTEGER DEFAULT 0,
    congelado INTEGER DEFAULT 0,              -- 0/1 (SQLite no tiene BOOLEAN)

    creado_en TEXT DEFAULT (datetime('now')),
    actualizado_en TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_discrepancias_mesa_key ON discrepancias (mesa_key);
CREATE INDEX IF NOT EXISTS idx_discrepancias_estado ON discrepancias (estado);
CREATE INDEX IF NOT EXISTS idx_discrepancias_prioridad ON discrepancias (prioridad);

-- ---------------------------------------------------------------------
-- votos_verificacion_ciudadana: cada voto individual sobre una discrepancia
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS votos_verificacion_ciudadana (
    id TEXT PRIMARY KEY,  -- UUID como TEXT
    discrepancia_id TEXT NOT NULL REFERENCES discrepancias(id),

    votante_id TEXT,                          -- referencia a usuario autenticado
    votante_ip_hash TEXT,

    voto TEXT NOT NULL CHECK (voto IN ('confirma_legitimo','confirma_anomalo')),
    comentario TEXT,
    peso_reputacion REAL DEFAULT 1.00,        -- multiplicador de peso del voto

    anulado INTEGER DEFAULT 0,
    anulado_razon TEXT,

    creado_en TEXT DEFAULT (datetime('now')),

    UNIQUE (discrepancia_id, votante_id)       -- 1 voto por usuario por discrepancia
);

CREATE INDEX IF NOT EXISTS idx_votos_discrepancia ON votos_verificacion_ciudadana (discrepancia_id);

-- ---------------------------------------------------------------------
-- configuracion_sistema: umbrales ajustables sin tocar código
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS configuracion_sistema (
    clave TEXT PRIMARY KEY,
    valor TEXT NOT NULL,
    descripcion TEXT,
    actualizado_en TEXT DEFAULT (datetime('now'))
);

INSERT INTO configuracion_sistema (clave, valor, descripcion) VALUES
    ('umbral_min_votos', '5', 'Número mínimo de votos ciudadanos para evaluar consenso'),
    ('umbral_consenso_pct', '0.80', 'Porcentaje mínimo de consenso en una dirección para congelar estado'),
    ('capa1_score_revision', '0.60', 'Score mínimo de Capa 1 para enviar celda a Capa 2'),
    ('capa1_score_prioridad_alta', '0.85', 'Score mínimo de Capa 1 para marcar prioridad alta directa');

-- ---------------------------------------------------------------------
-- Vista: resumen_departamento — alimenta el mapa del dashboard
-- Nota: En SQLite, las vistas son read-only y no soportan LEFT JOINs complejos
-- con funciones de agregación avanzadas de la misma forma. Simplificamos.
-- ---------------------------------------------------------------------
CREATE VIEW IF NOT EXISTS resumen_departamento AS
SELECT
    a.codigo_departamento,
    d.nombre_departamento,
    COUNT(DISTINCT a.mesa_key) AS total_mesas,
    COUNT(DISTINCT ec.mesa_key) AS mesas_con_evidencia_ciudadana,
    COUNT(DISTINCT disc.id) AS total_discrepancias,
    -- SQLite no soporta FILTER en agregaciones de la misma forma que PostgreSQL
    -- Usamos subconsultas en su lugar
    (SELECT COUNT(DISTINCT d2.id) FROM discrepancias d2 WHERE d2.mesa_key = a.mesa_key AND d2.estado = 'por_verificar') AS discrepancias_por_verificar
FROM actas_oficiales a
LEFT JOIN divipole_departamento d ON d.codigo_departamento = a.codigo_departamento
LEFT JOIN evidencia_ciudadana ec ON ec.mesa_key = a.mesa_key
LEFT JOIN discrepancias disc ON disc.mesa_key = a.mesa_key
GROUP BY a.codigo_departamento, d.nombre_departamento;

-- ---------------------------------------------------------------------
-- Vista: mesas_legitimas — mesas sin discrepancias activas o ya descartadas
-- ---------------------------------------------------------------------
CREATE VIEW IF NOT EXISTS mesas_legitimas AS
SELECT a.mesa_key, a.codigo_departamento, a.codigo_municipio, a.zona, a.puesto, a.mesa,
       a.lugar_votacion
FROM actas_oficiales a
WHERE a.flag_aritmetica_excede_total = 0
  AND a.flag_aritmetica_no_coincide = 0
  AND a.flag_qr_metadata_mismatch = 0
  AND NOT EXISTS (
      SELECT 1 FROM discrepancias d
      WHERE d.mesa_key = a.mesa_key
        AND d.estado IN ('por_verificar', 'verificado_anomalo')
  );

-- ---------------------------------------------------------------------
-- Trigger: actualizar contadores de votos en discrepancias y evaluar consenso
-- Nota: En SQLite, los triggers son más limitados que PostgreSQL.
-- Simulamos el comportamiento con un trigger básico.
-- ---------------------------------------------------------------------
CREATE TRIGGER IF NOT EXISTS trg_voto_actualiza_consenso
AFTER INSERT ON votos_verificacion_ciudadana
BEGIN
    -- Actualizar contadores de votos en discrepancias
    UPDATE discrepancias
    SET votos_confirma = (
        SELECT COUNT(*) FROM votos_verificacion_ciudadana
        WHERE discrepancia_id = NEW.discrepancia_id AND voto = 'confirma_legitimo' AND anulado = 0
    ),
    votos_rechaza = (
        SELECT COUNT(*) FROM votos_verificacion_ciudadana
        WHERE discrepancia_id = NEW.discrepancia_id AND voto = 'confirma_anomalo' AND anulado = 0
    ),
    actualizado_en = datetime('now')
    WHERE id = NEW.discrepancia_id;

    -- Evaluar consenso (lógica simplificada para SQLite)
    -- Nota: El umbral completo se implementa mejor en la capa de aplicación para SQLite
END;

-- Trigger para bloquear votos en discrepancias congeladas
CREATE TRIGGER IF NOT EXISTS trg_bloquear_voto_congelado
BEFORE INSERT ON votos_verificacion_ciudadana
BEGIN
    -- Nota: SQLite no permite acceso a otras tablas en BEFORE INSERT triggers de forma directa
    -- La lógica de bloqueo se implementa mejor en la capa de aplicación para SQLite
    -- Este trigger es un placeholder que se puede activar con lógica adicional
    SELECT CASE
        WHEN (SELECT congelado FROM discrepancias WHERE id = NEW.discrepancia_id) = 1
        THEN RAISE(ABORT, 'Esta discrepancia ya fue verificada y está congelada para nuevos votos.')
    END;
END;