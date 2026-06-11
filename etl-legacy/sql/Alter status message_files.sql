ALTER TABLE dbo.message_files
ADD status VARCHAR(20) NOT NULL
    CONSTRAINT DF_message_files_status DEFAULT ('ok');

ALTER TABLE dbo.message_files
ADD CONSTRAINT CK_message_files_status
CHECK (status IN ('ok','forbidden','not_found','error','skipped'));

CREATE INDEX IX_message_files_tenant_status_type
ON dbo.message_files(tenant_id, status, file_type)
INCLUDE (downloaded_at, original_url, file_path, messageId);

-- Permitir file_path NULL para poder registrar fallas sin ruta local
-- (si ya es NULL, esto no hace nada)
IF EXISTS (
  SELECT 1
  FROM sys.columns
  WHERE object_id = OBJECT_ID('dbo.message_files')
    AND name = 'file_path'
    AND is_nullable = 0
)
BEGIN
  ALTER TABLE dbo.message_files
    ALTER COLUMN file_path NVARCHAR(500) NULL;
END;


--/// ESTO NO SE REQUIERE YA QUE ESTA LA VISTA "vw_agent_metrics_arg"
-- Opción A: Columnas calculadas (computed, persisted)
-- Así no tienes que mantenerlas manualmente: SQL Server se encarga de rellenarlas cada vez que cambien las fechas origen.
ALTER TABLE dbo.agent_metrics
ADD
  sessionCreationTime_arg_date AS CONVERT(DATE,  SWITCHOFFSET(sessionCreationTime, '-03:00')) PERSISTED,
  sessionCreationTime_arg_time AS CONVERT(TIME,  SWITCHOFFSET(sessionCreationTime, '-03:00')) PERSISTED,
  closedTime_arg_date          AS CONVERT(DATE,  SWITCHOFFSET(closedTime,           '-03:00')) PERSISTED,
  closedTime_arg_time          AS CONVERT(TIME,  SWITCHOFFSET(closedTime,           '-03:00')) PERSISTED;
-- PERSISTED: almacena el resultado en disco (pesas un poco más, pero es más rápido de leer).
-- Si no quieres PERSISTED, quita esa palabra y SQL Server calculará sobre la marcha.