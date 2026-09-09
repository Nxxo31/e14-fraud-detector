-- schema_postgresql.sql — Schema completo para Supabase
-- Adaptado del schema.sql original del usuario
-- Usar en Supabase Dashboard > SQL Editor

-- =====================================================================
-- schema.sql — Auditoría Ciudadana de Actas E-14
-- PostgreSQL 14+
-- =====================================================================

-- Extensiones
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ---------------------------------------------------------------------
-- Tabla de referencia: divipola (departamentos y municipios)
-- Poblar una sola vez con la codificación oficial DIVIPOLA.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS divipole_departamento (
    codigo_departamento TEXT PRIMARY KEY,
    nombre_departamento TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS divipole_municipio (
    codigo_departamento TEXT NOT NULL REFERENCES divipole_departamento(codigo_departamento),
    codigo_municipio TEXT NOT NULL,
    nombre_municipio TEXT NOT NULL,
    PRIMARY KEY (codigo_departamento, codigo_municipio)
);

-- ---------------------------------------------------------------------
-- actas_oficiales
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS actas_oficiales (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

    mesa_key TEXT NOT NULL,
    codigo_departamento TEXT NOT NULL,
    codigo_municipio TEXT NOT NULL,
    zona TEXT,
    puesto TEXT,
    mesa TEXT NOT NULL,
    lugar_votacion TEXT,

    tipo_ejemplar TEXT NOT NULL CHECK (tipo_ejemplar IN ('delegados','claveros','transmision')),

    pdf_url TEXT,
    pdf_storage_path TEXT,
    kit_numero TEXT,
    formulario_numero TEXT,
    version_formato TEXT,

    qr_raw_value TEXT,
    qr_decoded_match BOOLEAN,

    paginas_total INT,
    paginas_esperadas INT DEFAULT 2,
    pagina_2_vacia BOOLEAN,
    firmas_detectadas INT,

    total_votantes_e11 INT,
    total_votos_urna INT,
    total_votos_incinerados INT,

    votos_candidato_1 INT,
    votos_candidato_2 INT,
    votos_blanco INT,
    votos_nulos INT,
    votos_no_marcados INT,
    suma_total_calculada INT,

    flag_aritmetica_excede_total BOOLEAN DEFAULT FALSE,
    flag_aritmetica_no_coincide BOOLEAN DEFAULT FALSE,
    flag_nivelacion_inconsistente BOOLEAN DEFAULT FALSE,
    flag_paginas_incompletas BOOLEAN DEFAULT FALSE,
    flag_firmas_insuficientes BOOLEAN DEFAULT FALSE,
    flag_qr_metadata_mismatch BOOLEAN DEFAULT FALSE,

    capa_maxima_procesada INT DEFAULT 0,
    estado_procesamiento TEXT DEFAULT 'pendiente'
        CHECK (estado_procesamiento IN ('pendiente','procesando','completado','error')),

    creado_en TIMESTAMPTZ DEFAULT now(),
    actualizado_en TIMESTAMPTZ DEFAULT now(),

    UNIQUE (mesa_key, tipo_ejemplar)
);

CREATE INDEX IF NOT EXISTS idx_actas_mesa_key ON actas_oficiales (mesa_key);
CREATE INDEX IF NOT EXISTS idx_actas_departamento ON actas_oficiales (codigo_departamento);
CREATE INDEX IF NOT EXISTS idx_actas_estado_proc ON actas_oficiales (estado_procesamiento);
CREATE INDEX IF NOT EXISTS idx_actas_flags ON actas_oficiales (flag_aritmetica_excede_total, flag_aritmetica_no_coincide);

-- ---------------------------------------------------------------------
-- evidencia_ciudadana
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS evidencia_ciudadana (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

    mesa_key TEXT NOT NULL,
    imagen_url TEXT NOT NULL,
    imagen_storage_path TEXT,

    aportante_id UUID,
    aportante_ip_hash TEXT,

    votos_extraidos JSONB,
    metodo_extraccion TEXT CHECK (metodo_extraccion IN ('manual','ocr_zona','vlm','mixto')),
    confianza_extraccion NUMERIC(4,3),

    estado_revision TEXT DEFAULT 'pendiente'
        CHECK (estado_revision IN ('pendiente','procesada','rechazada_calidad')),

    creado_en TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_evidencia_mesa_key ON evidencia_ciudadana (mesa_key);
CREATE INDEX IF NOT EXISTS idx_evidencia_estado ON evidencia_ciudadana (estado_revision);

-- ---------------------------------------------------------------------
-- cola_procesamiento
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS cola_procesamiento (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    mesa_key TEXT NOT NULL,
    acta_id UUID REFERENCES actas_oficiales(id),

    capa_actual INT NOT NULL DEFAULT 0 CHECK (capa_actual IN (0,1,2)),
    estado_slot TEXT NOT NULL DEFAULT 'pendiente'
        CHECK (estado_slot IN ('pendiente','tomado','procesando','completado','error')),

    worker_id TEXT,
    intentos INT DEFAULT 0,
    max_intentos INT DEFAULT 3,
    ultimo_error TEXT,

    tomado_en TIMESTAMPTZ,
    completado_en TIMESTAMPTZ,
    creado_en TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_cola_estado_capa ON cola_procesamiento (estado_slot, capa_actual);
CREATE INDEX IF NOT EXISTS idx_cola_mesa_key ON cola_procesamiento (mesa_key);

-- Función helper para tomar el siguiente slot disponible de forma segura
CREATE OR REPLACE FUNCTION tomar_siguiente_slot(p_worker_id TEXT, p_capa INT)
RETURNS SETOF cola_procesamiento AS $$
BEGIN
    RETURN QUERY
    UPDATE cola_procesamiento
    SET estado_slot = 'tomado',
        worker_id = p_worker_id,
        tomado_en = now()
    WHERE id = (
        SELECT id FROM cola_procesamiento
        WHERE estado_slot = 'pendiente' AND capa_actual = p_capa
        ORDER BY creado_en
        LIMIT 1
        FOR UPDATE SKIP LOCKED
    )
    RETURNING *;
END;
$$ LANGUAGE plpgsql;

-- ---------------------------------------------------------------------
-- discrepancias
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS discrepancias (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

    mesa_key TEXT NOT NULL,
    acta_oficial_id UUID REFERENCES actas_oficiales(id),
    evidencia_ciudadana_id UUID REFERENCES evidencia_ciudadana(id),

    campo_afectado TEXT NOT NULL,
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

    score_capa0 NUMERIC(4,3),
    score_capa1 NUMERIC(4,3),
    score_capa2 NUMERIC(4,3),

    razon_flag TEXT,
    evidencia_imagen_recorte_url TEXT,

    prioridad TEXT DEFAULT 'media' CHECK (prioridad IN ('baja','media','alta')),

    estado TEXT NOT NULL DEFAULT 'por_verificar'
        CHECK (estado IN ('por_verificar','verificado_legitimo','verificado_anomalo')),

    votos_confirma INT DEFAULT 0,
    votos_rechaza INT DEFAULT 0,
    congelado BOOLEAN DEFAULT FALSE,

    creado_en TIMESTAMPTZ DEFAULT now(),
    actualizado_en TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_discrepancias_mesa_key ON discrepancias (mesa_key);
CREATE INDEX IF NOT EXISTS idx_discrepancias_estado ON discrepancias (estado);
CREATE INDEX IF NOT EXISTS idx_discrepancias_prioridad ON discrepancias (prioridad);

-- ---------------------------------------------------------------------
-- votos_verificacion_ciudadana
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS votos_verificacion_ciudadana (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    discrepancia_id UUID NOT NULL REFERENCES discrepancias(id),

    votante_id UUID,
    votante_ip_hash TEXT,

    voto TEXT NOT NULL CHECK (voto IN ('confirma_legitimo','confirma_anomalo')),
    comentario TEXT,
    peso_reputacion NUMERIC(3,2) DEFAULT 1.00,

    anulado BOOLEAN DEFAULT FALSE,
    anulado_razon TEXT,

    creado_en TIMESTAMPTZ DEFAULT now(),

    UNIQUE (discrepancia_id, votante_id)
);

CREATE INDEX IF NOT EXISTS idx_votos_discrepancia ON votos_verificacion_ciudadana (discrepancia_id);

-- ---------------------------------------------------------------------
-- configuracion_sistema
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS configuracion_sistema (
    clave TEXT PRIMARY KEY,
    valor TEXT NOT NULL,
    descripcion TEXT,
    actualizado_en TIMESTAMPTZ DEFAULT now()
);

INSERT INTO configuracion_sistema (clave, valor, descripcion) VALUES
    ('umbral_min_votos', '5', 'Número mínimo de votos ciudadanos para evaluar consenso'),
    ('umbral_consenso_pct', '0.80', 'Porcentaje mínimo de consenso en una dirección para congelar estado'),
    ('capa1_score_revision', '0.60', 'Score mínimo de Capa 1 para enviar celda a Capa 2'),
    ('capa1_score_prioridad_alta', '0.85', 'Score mínimo de Capa 1 para marcar prioridad alta directa');

-- ---------------------------------------------------------------------
-- Vista: resumen_departamento
-- ---------------------------------------------------------------------
CREATE OR REPLACE VIEW resumen_departamento AS
SELECT
    a.codigo_departamento,
    d.nombre_departamento,
    COUNT(DISTINCT a.mesa_key) AS total_mesas,
    COUNT(DISTINCT ec.mesa_key) AS mesas_con_evidencia_ciudadana,
    COUNT(DISTINCT disc.id) AS total_discrepancias,
    COUNT(DISTINCT disc.id) FILTER (WHERE disc.estado = 'por_verificar') AS discrepancias_por_verificar,
    COUNT(DISTINCT disc.id) FILTER (WHERE disc.estado = 'verificado_legitimo') AS discrepancias_verificadas_legitimas,
    COUNT(DISTINCT disc.id) FILTER (WHERE disc.estado = 'verificado_anomalo') AS discrepancias_verificadas_anomalas,
    ROUND(
        100.0 * COUNT(DISTINCT disc.id) FILTER (WHERE disc.estado != 'por_verificar')
        / GREATEST(COUNT(DISTINCT disc.id), 1), 2
    ) AS porcentaje_verificado,
    ROUND(
        100.0 * COUNT(DISTINCT disc.id) FILTER (WHERE disc.estado = 'por_verificar')
        / GREATEST(COUNT(DISTINCT disc.id), 1), 2
    ) AS porcentaje_por_verificar
FROM actas_oficiales a
LEFT JOIN divipole_departamento d ON d.codigo_departamento = a.codigo_departamento
LEFT JOIN evidencia_ciudadana ec ON ec.mesa_key = a.mesa_key
LEFT JOIN discrepancias disc ON disc.mesa_key = a.mesa_key
GROUP BY a.codigo_departamento, d.nombre_departamento;

-- ---------------------------------------------------------------------
-- Vista: mesas_legitimas
-- ---------------------------------------------------------------------
CREATE OR REPLACE VIEW mesas_legitimas AS
SELECT a.mesa_key, a.codigo_departamento, a.codigo_municipio, a.zona, a.puesto, a.mesa,
       a.lugar_votacion
FROM actas_oficiales a
WHERE a.flag_aritmetica_excede_total = FALSE
  AND a.flag_aritmetica_no_coincide = FALSE
  AND a.flag_qr_metadata_mismatch = FALSE
  AND NOT EXISTS (
      SELECT 1 FROM discrepancias d
      WHERE d.mesa_key = a.mesa_key
        AND d.estado IN ('por_verificar', 'verificado_anomalo')
  );

-- ---------------------------------------------------------------------
-- Trigger: actualizar contadores de votos en discrepancias y evaluar consenso
-- ---------------------------------------------------------------------
CREATE OR REPLACE FUNCTION fn_actualizar_consenso_discrepancia()
RETURNS TRIGGER AS $$
DECLARE
    v_confirma INT;
    v_rechaza INT;
    v_total INT;
    v_umbral_min INT;
    v_umbral_pct NUMERIC;
BEGIN
    SELECT valor::INT INTO v_umbral_min FROM configuracion_sistema WHERE clave = 'umbral_min_votos';
    SELECT valor::NUMERIC INTO v_umbral_pct FROM configuracion_sistema WHERE clave = 'umbral_consenso_pct';

    SELECT
        COUNT(*) FILTER (WHERE voto = 'confirma_legitimo'),
        COUNT(*) FILTER (WHERE voto = 'confirma_anomalo')
    INTO v_confirma, v_rechaza
    FROM votos_verificacion_ciudadana
    WHERE discrepancia_id = NEW.discrepancia_id AND anulado = FALSE;

    v_total := v_confirma + v_rechaza;

    UPDATE discrepancias
    SET votos_confirma = v_confirma,
        votos_rechaza = v_rechaza,
        actualizado_en = now()
    WHERE id = NEW.discrepancia_id;

    IF v_total >= v_umbral_min AND NOT (SELECT congelado FROM discrepancias WHERE id = NEW.discrepancia_id) THEN
        IF v_confirma::NUMERIC / v_total >= v_umbral_pct THEN
            UPDATE discrepancias SET estado = 'verificado_legitimo', congelado = TRUE WHERE id = NEW.discrepancia_id;
        ELSIF v_rechaza::NUMERIC / v_total >= v_umbral_pct THEN
            UPDATE discrepancias SET estado = 'verificado_anomalo', congelado = TRUE WHERE id = NEW.discrepancia_id;
        END IF;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_voto_actualiza_consenso
AFTER INSERT ON votos_verificacion_ciudadana
FOR EACH ROW
EXECUTE FUNCTION fn_actualizar_consenso_discrepancia();

-- ---------------------------------------------------------------------
-- Trigger: impedir votos sobre discrepancias ya congeladas
-- ---------------------------------------------------------------------
CREATE OR REPLACE FUNCTION fn_bloquear_voto_si_congelado()
RETURNS TRIGGER AS $$
BEGIN
    IF (SELECT congelado FROM discrepancias WHERE id = NEW.discrepancia_id) THEN
        RAISE EXCEPTION 'Esta discrepancia ya fue verificada y está congelada para nuevos votos.';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_bloquear_voto_congelado
BEFORE INSERT ON votos_verificacion_ciudadana
FOR EACH ROW
EXECUTE FUNCTION fn_bloquear_voto_si_congelado();

-- ---------------------------------------------------------------------
-- Poblar DIVIPOLA Antioquia
-- ---------------------------------------------------------------------
INSERT INTO divipole_departamento (codigo_departamento, nombre_departamento) VALUES ('01', 'Antioquia')
ON CONFLICT DO NOTHING;

INSERT INTO divipole_municipio (codigo_departamento, codigo_municipio, nombre_municipio) VALUES
    ('01', '034', 'Anzá'),
    ('01', '280', 'Turbo')
ON CONFLICT DO NOTHING;