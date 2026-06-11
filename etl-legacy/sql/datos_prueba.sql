/* ============================================================================
   DATOS DE PRUEBA - KoalaETL
   Contexto: bot de WhatsApp de una aseguradora (tenant = GrupoRimoldi)
   ----------------------------------------------------------------------------
   - Respeta el orden de las FKs (tenants -> agents/queues -> ... -> messages -> subtablas)
   - NO inserta columnas IDENTITY (performanceId, mediaId, itemIndex)
   - Respeta el CHECK de message_files.status ('ok','forbidden','not_found','error','skipped')
   - Pensado para correr sobre la DB ya creada con el esquema + el ALTER de status
   - Idempotente-ish: borra primero los datos del tenant de prueba (ver bloque LIMPIEZA)
   ============================================================================ */

USE KoalaETL;
GO

SET NOCOUNT ON;
SET XACT_ABORT ON;

DECLARE @t NVARCHAR(50) = N'GrupoRimoldi';

BEGIN TRAN;

/* ---------------------------------------------------------------------------
   LIMPIEZA (orden inverso a las FKs) - permite re-ejecutar el script
   --------------------------------------------------------------------------- */
DELETE FROM dbo.message_files          WHERE tenant_id = @t;
DELETE FROM dbo.encryptionParams       WHERE tenant_id = @t;
DELETE FROM dbo.message_call           WHERE tenant_id = @t;
DELETE FROM dbo.message_location       WHERE tenant_id = @t;
DELETE FROM dbo.message_media          WHERE tenant_id = @t;
DELETE FROM dbo.message_carouselItems  WHERE tenant_id = @t;
DELETE FROM dbo.message_buttons        WHERE tenant_id = @t;
DELETE FROM dbo.message_content        WHERE tenant_id = @t;
DELETE FROM dbo.messages               WHERE tenant_id = @t;
DELETE FROM dbo.chat_tags              WHERE tenant_id = @t;
DELETE FROM dbo.chat_variables         WHERE tenant_id = @t;
DELETE FROM dbo.chat_details           WHERE tenant_id = @t;
DELETE FROM dbo.agent_metrics          WHERE tenant_id = @t;
DELETE FROM dbo.agent_performance      WHERE tenant_id = @t;
DELETE FROM dbo.agent_performance_queues WHERE tenant_id = @t;
DELETE FROM dbo.chats                  WHERE tenant_id = @t;
DELETE FROM dbo.queues                 WHERE tenant_id = @t;
DELETE FROM dbo.agents                 WHERE tenant_id = @t;
DELETE FROM dbo.tenants                WHERE tenant_id = @t;

/* ---------------------------------------------------------------------------
   1) TENANT
   --------------------------------------------------------------------------- */
INSERT INTO dbo.tenants (tenant_id, tenant_name) VALUES
  (@t, N'Grupo Rimoldi Seguros');

/* ---------------------------------------------------------------------------
   2) AGENTS
   --------------------------------------------------------------------------- */
INSERT INTO dbo.agents (tenant_id, agentEmail, agentName, role) VALUES
  (@t, N'ana.gomez@gruporimoldi.com',       N'Ana Gómez',        N'agent'),
  (@t, N'carlos.ruiz@gruporimoldi.com',     N'Carlos Ruiz',      N'agent'),
  (@t, N'lucia.fernandez@gruporimoldi.com', N'Lucía Fernández',  N'supervisor'),
  (@t, N'martin.lopez@gruporimoldi.com',    N'Martín López',     N'agent');

/* ---------------------------------------------------------------------------
   3) QUEUES
   --------------------------------------------------------------------------- */
INSERT INTO dbo.queues (tenant_id, queue) VALUES
  (@t, N'Siniestros'),
  (@t, N'Ventas'),
  (@t, N'Atencion_Cliente');

/* ---------------------------------------------------------------------------
   4) AGENT_PERFORMANCE_QUEUES (relación M–N)
   --------------------------------------------------------------------------- */
INSERT INTO dbo.agent_performance_queues (tenant_id, agentEmail, queue) VALUES
  (@t, N'ana.gomez@gruporimoldi.com',       N'Siniestros'),
  (@t, N'ana.gomez@gruporimoldi.com',       N'Atencion_Cliente'),
  (@t, N'carlos.ruiz@gruporimoldi.com',     N'Ventas'),
  (@t, N'carlos.ruiz@gruporimoldi.com',     N'Atencion_Cliente'),
  (@t, N'lucia.fernandez@gruporimoldi.com', N'Siniestros'),
  (@t, N'lucia.fernandez@gruporimoldi.com', N'Ventas'),
  (@t, N'martin.lopez@gruporimoldi.com',    N'Atencion_Cliente');

/* ---------------------------------------------------------------------------
   5) AGENT_PERFORMANCE (performanceId es IDENTITY -> no se inserta)
   --------------------------------------------------------------------------- */
INSERT INTO dbo.agent_performance (tenant_id, agentEmail, state, checkin, checkout) VALUES
  (@t, N'ana.gomez@gruporimoldi.com',       N'online',  '2025-03-03T09:00:00', '2025-03-03T17:05:00'),
  (@t, N'ana.gomez@gruporimoldi.com',       N'online',  '2025-03-04T09:02:00', '2025-03-04T17:00:00'),
  (@t, N'carlos.ruiz@gruporimoldi.com',     N'online',  '2025-03-03T08:55:00', '2025-03-03T16:50:00'),
  (@t, N'carlos.ruiz@gruporimoldi.com',     N'away',    '2025-03-04T09:10:00', '2025-03-04T17:30:00'),
  (@t, N'lucia.fernandez@gruporimoldi.com', N'online',  '2025-03-03T10:00:00', '2025-03-03T18:00:00'),
  (@t, N'martin.lopez@gruporimoldi.com',    N'online',  '2025-03-04T09:00:00', '2025-03-04T17:00:00');

/* ---------------------------------------------------------------------------
   7) CHATS  (channel WhatsApp; chatId/contactId = teléfono)
   --------------------------------------------------------------------------- */
INSERT INTO dbo.chats (tenant_id, chatId, channelId, contactId) VALUES
  (@t, N'549114455001', N'whatsapp', N'+549114455001'),
  (@t, N'549114455002', N'whatsapp', N'+549114455002'),
  (@t, N'549114455003', N'whatsapp', N'+549114455003'),
  (@t, N'549114455004', N'whatsapp', N'+549114455004'),
  (@t, N'549114455005', N'whatsapp', N'+549114455005');

/* ---------------------------------------------------------------------------
   8) CHAT_DETAILS
   --------------------------------------------------------------------------- */
INSERT INTO dbo.chat_details
  (tenant_id, chatId, creationTime, lastSessionCreationTime, externalId, firstName, lastName,
   country, email, whatsAppWindowCloseDatetime, queueId, agentId, onHoldAgentId,
   lastUserMessageDatetime, isTester, isBotMuted, isBanned) VALUES
  (@t, N'549114455001', '2025-03-03T09:15:00', '2025-03-03T09:15:00', N'POL-100023', N'Juan',    N'Pérez',    'AR', N'juan.perez@gmail.com',    '2025-03-04T09:15:00', N'Siniestros',       N'AG001', NULL,    '2025-03-03T09:40:00', 0, 0, 0),
  (@t, N'549114455002', '2025-03-03T11:00:00', '2025-03-03T11:00:00', N'POL-100481', N'María',   N'González', 'AR', N'maria.gonzalez@gmail.com','2025-03-04T11:00:00', N'Ventas',           N'AG002', NULL,    '2025-03-03T11:20:00', 0, 0, 0),
  (@t, N'549114455003', '2025-03-04T14:30:00', '2025-03-04T14:30:00', NULL,          N'Roberto', N'Díaz',     'AR', NULL,                       '2025-03-05T14:30:00', N'Atencion_Cliente', N'AG004', NULL,    '2025-03-04T14:55:00', 0, 0, 0),
  (@t, N'549114455004', '2025-03-04T16:10:00', '2025-03-04T16:10:00', N'POL-100902', N'Sofía',   N'Romero',   'AR', N'sofia.romero@gmail.com',  '2025-03-05T16:10:00', N'Siniestros',       N'AG003', N'AG001','2025-03-04T16:45:00', 0, 0, 0),
  (@t, N'549114455005', '2025-03-05T10:05:00', '2025-03-05T10:05:00', NULL,          N'Test',    N'QA',       'AR', NULL,                       '2025-03-06T10:05:00', N'Atencion_Cliente', NULL,    NULL,    '2025-03-05T10:08:00', 1, 0, 0);

/* ---------------------------------------------------------------------------
   9) CHAT_VARIABLES
   --------------------------------------------------------------------------- */
INSERT INTO dbo.chat_variables (tenant_id, chatId, var_key, var_value) VALUES
  (@t, N'549114455001', N'nro_poliza',  N'POL-100023'),
  (@t, N'549114455001', N'tipo_seguro', N'Automotor'),
  (@t, N'549114455002', N'nro_poliza',  N'POL-100481'),
  (@t, N'549114455002', N'tipo_seguro', N'Hogar'),
  (@t, N'549114455004', N'nro_poliza',  N'POL-100902'),
  (@t, N'549114455004', N'tipo_seguro', N'Automotor'),
  (@t, N'549114455004', N'patente',     N'AB123CD');

/* ---------------------------------------------------------------------------
   10) CHAT_TAGS
   --------------------------------------------------------------------------- */
INSERT INTO dbo.chat_tags (tenant_id, chatId, tag) VALUES
  (@t, N'549114455001', N'siniestro'),
  (@t, N'549114455001', N'urgente'),
  (@t, N'549114455002', N'cotizacion'),
  (@t, N'549114455003', N'consulta'),
  (@t, N'549114455004', N'siniestro'),
  (@t, N'549114455004', N'granizo');

/* ---------------------------------------------------------------------------
   6) AGENT_METRICS  (FK queue -> queues; una fila por sesión)
   --------------------------------------------------------------------------- */
INSERT INTO dbo.agent_metrics
  (tenant_id, sessionId, chatId, sessionCreationTime, avgAttendingTime, avgResponseTime, queue,
   agentName, agentId, typification, closedTime, openSessions, closedSessions, onHold,
   opResponseTime, operatorResponses, sessionTransferIn, sessionTransferOut,
   sessionTransferOutNoMessages, closedWithNoMessages, timeoutNoMessages, agentTimeout,
   userTimeout, fromQueueAsignToOpAssigned, fromSessionStartToOpFirstResponse,
   fromQueueAsignToOpFirstResponse, fromOpAssignedToOpFirstResponse,
   fromQueueAsignToSessionClosed, fromOpAssignationToSessionClosed, sessionTimeout,
   conversationLink) VALUES
  (@t, N'SES-0001', N'549114455001', '2025-03-03T09:15:00', 320, 45, N'Siniestros',       N'Ana Gómez',       N'AG001', N'Denuncia siniestro', '2025-03-03T09:40:00', 0, 1, 0, 42, 6, 0, 0, 0, 0, 0, 0, 0, 30, 70, 70, 40, 1500, 1470, 0, N'https://go.botmaker.com/#/chats/549114455001'),
  (@t, N'SES-0002', N'549114455002', '2025-03-03T11:00:00', 280, 60, N'Ventas',           N'Carlos Ruiz',     N'AG002', N'Cotización',         '2025-03-03T11:20:00', 0, 1, 0, 55, 4, 0, 0, 0, 0, 0, 0, 0, 25, 90, 90, 65, 1200, 1175, 0, N'https://go.botmaker.com/#/chats/549114455002'),
  (@t, N'SES-0003', N'549114455003', '2025-03-04T14:30:00', 150, 38, N'Atencion_Cliente', N'Martín López',    N'AG004', N'Consulta general',   '2025-03-04T14:55:00', 0, 1, 0, 35, 3, 0, 0, 0, 0, 0, 0, 0, 20, 55, 55, 35, 1500, 1480, 0, N'https://go.botmaker.com/#/chats/549114455003'),
  (@t, N'SES-0004', N'549114455004', '2025-03-04T16:10:00', 600, 75, N'Siniestros',       N'Lucía Fernández', N'AG003', N'Siniestro granizo',  '2025-03-04T16:45:00', 0, 1, 1, 70, 9, 1, 0, 0, 0, 0, 0, 0, 40, 110, 110, 70, 2100, 2060, 0, N'https://go.botmaker.com/#/chats/549114455004'),
  (@t, N'SES-0005', N'549114455005', '2025-03-05T10:05:00', NULL, NULL, N'Atencion_Cliente', N'Ana Gómez',    N'AG001', NULL,                  NULL,                  1, 0, 0, NULL, 0, 0, 0, 0, 0, 0, 0, 0, NULL, NULL, NULL, NULL, NULL, NULL, 0, N'https://go.botmaker.com/#/chats/549114455005');

/* ---------------------------------------------------------------------------
   11) MESSAGES  (from: 'user' | 'bot' | 'agent'; queueId -> queues)
   --------------------------------------------------------------------------- */
INSERT INTO dbo.messages
  (tenant_id, id, creationTime, [from], agentId, queueId, sessionCreationTime, chatId, sessionId, whatsAppTemplateName) VALUES
  -- Chat 1 (Siniestros)
  (@t, N'MSG-0001', '2025-03-03T09:15:05', N'user',  NULL,    N'Siniestros', '2025-03-03T09:15:00', N'549114455001', N'SES-0001', NULL),
  (@t, N'MSG-0002', '2025-03-03T09:15:10', N'bot',   NULL,    N'Siniestros', '2025-03-03T09:15:00', N'549114455001', N'SES-0001', N'menu_bienvenida'),
  (@t, N'MSG-0003', '2025-03-03T09:16:00', N'user',  NULL,    N'Siniestros', '2025-03-03T09:15:00', N'549114455001', N'SES-0001', NULL),
  (@t, N'MSG-0004', '2025-03-03T09:18:30', N'agent', N'AG001', N'Siniestros', '2025-03-03T09:15:00', N'549114455001', N'SES-0001', NULL),
  (@t, N'MSG-0005', '2025-03-03T09:20:00', N'user',  NULL,    N'Siniestros', '2025-03-03T09:15:00', N'549114455001', N'SES-0001', NULL),
  -- Chat 2 (Ventas)
  (@t, N'MSG-0006', '2025-03-03T11:00:05', N'user',  NULL,    N'Ventas', '2025-03-03T11:00:00', N'549114455002', N'SES-0002', NULL),
  (@t, N'MSG-0007', '2025-03-03T11:00:12', N'bot',   NULL,    N'Ventas', '2025-03-03T11:00:00', N'549114455002', N'SES-0002', N'cotizacion_inicio'),
  (@t, N'MSG-0008', '2025-03-03T11:02:00', N'agent', N'AG002', N'Ventas', '2025-03-03T11:00:00', N'549114455002', N'SES-0002', NULL),
  -- Chat 3 (Atencion)
  (@t, N'MSG-0009', '2025-03-04T14:30:05', N'user',  NULL,    N'Atencion_Cliente', '2025-03-04T14:30:00', N'549114455003', N'SES-0003', NULL),
  (@t, N'MSG-0010', '2025-03-04T14:31:00', N'agent', N'AG004', N'Atencion_Cliente', '2025-03-04T14:30:00', N'549114455003', N'SES-0003', NULL),
  -- Chat 4 (Siniestros con foto/ubicación)
  (@t, N'MSG-0011', '2025-03-04T16:10:05', N'user',  NULL,    N'Siniestros', '2025-03-04T16:10:00', N'549114455004', N'SES-0004', NULL),
  (@t, N'MSG-0012', '2025-03-04T16:12:00', N'user',  NULL,    N'Siniestros', '2025-03-04T16:10:00', N'549114455004', N'SES-0004', NULL),  -- foto
  (@t, N'MSG-0013', '2025-03-04T16:13:00', N'user',  NULL,    N'Siniestros', '2025-03-04T16:10:00', N'549114455004', N'SES-0004', NULL),  -- ubicación
  (@t, N'MSG-0014', '2025-03-04T16:15:00', N'user',  NULL,    N'Siniestros', '2025-03-04T16:10:00', N'549114455004', N'SES-0004', NULL),  -- audio
  (@t, N'MSG-0015', '2025-03-04T16:20:00', N'agent', N'AG003', N'Siniestros', '2025-03-04T16:10:00', N'549114455004', N'SES-0004', NULL),
  -- Chat 5 (Tester)
  (@t, N'MSG-0016', '2025-03-05T10:05:05', N'user',  NULL,    N'Atencion_Cliente', '2025-03-05T10:05:00', N'549114455005', N'SES-0005', NULL);

/* ---------------------------------------------------------------------------
   12) MESSAGE_CONTENT
   --------------------------------------------------------------------------- */
INSERT INTO dbo.message_content (tenant_id, messageId, [type], text, selectedButton, originalText, originalAudioUrl) VALUES
  (@t, N'MSG-0001', N'text',     N'Hola, tuve un choque y quiero hacer la denuncia', NULL, NULL, NULL),
  (@t, N'MSG-0002', N'buttons',  N'¡Hola! ¿Sobre qué querés gestionar?', NULL, NULL, NULL),
  (@t, N'MSG-0003', N'text',     N'Siniestro', N'Siniestro', NULL, NULL),
  (@t, N'MSG-0004', N'text',     N'Buen día Juan, soy Ana. Contame qué pasó.', NULL, NULL, NULL),
  (@t, N'MSG-0005', N'text',     N'Me chocaron de atrás en Av. Corrientes', NULL, NULL, NULL),
  (@t, N'MSG-0006', N'text',     N'Hola, quiero cotizar un seguro de hogar', NULL, NULL, NULL),
  (@t, N'MSG-0007', N'text',     N'¡Perfecto! Te paso con un asesor de Ventas.', NULL, NULL, NULL),
  (@t, N'MSG-0008', N'text',     N'Hola María, soy Carlos. ¿Qué metros tiene la propiedad?', NULL, NULL, NULL),
  (@t, N'MSG-0009', N'text',     N'¿Cómo descargo mi póliza?', NULL, NULL, NULL),
  (@t, N'MSG-0010', N'text',     N'Te la envío por mail ahora mismo.', NULL, NULL, NULL),
  (@t, N'MSG-0011', N'text',     N'Cayó granizo y me rompió el parabrisas', NULL, NULL, NULL),
  (@t, N'MSG-0012', N'image',    N'Foto del daño', NULL, NULL, NULL),
  (@t, N'MSG-0013', N'location', N'Ubicación del vehículo', NULL, NULL, NULL),
  (@t, N'MSG-0014', N'audio',    NULL, NULL, N'Te mando un audio explicando', N'https://storage.googleapis.com/storage.botmaker.com/GrupoRimoldi/MSG-0014/audio/nota.ogg'),
  (@t, N'MSG-0015', N'text',     N'Recibido Sofía, derivo el caso a un perito.', NULL, NULL, NULL),
  (@t, N'MSG-0016', N'text',     N'mensaje de prueba QA', NULL, NULL, NULL);

/* ---------------------------------------------------------------------------
   13) MESSAGE_BUTTONS (del menú del bot)
   --------------------------------------------------------------------------- */
INSERT INTO dbo.message_buttons (tenant_id, messageId, button) VALUES
  (@t, N'MSG-0002', N'Siniestro'),
  (@t, N'MSG-0002', N'Cotizar'),
  (@t, N'MSG-0002', N'Atención al cliente');

/* ---------------------------------------------------------------------------
   15) MESSAGE_MEDIA (mediaId IDENTITY -> no se inserta)
   --------------------------------------------------------------------------- */
INSERT INTO dbo.message_media (tenant_id, messageId, caption, url) VALUES
  (@t, N'MSG-0012', N'Parabrisas dañado por granizo', N'https://storage.googleapis.com/storage.botmaker.com/GrupoRimoldi/MSG-0012/media/dano_parabrisas.jpg');

/* ---------------------------------------------------------------------------
   16) MESSAGE_LOCATION
   --------------------------------------------------------------------------- */
INSERT INTO dbo.message_location (tenant_id, messageId, latitude, longitude, name, address) VALUES
  (@t, N'MSG-0013', N'-34.603722', N'-58.381592', N'Obelisco', N'Av. 9 de Julio, CABA, Argentina');

/* ---------------------------------------------------------------------------
   17) MESSAGE_CALL
   --------------------------------------------------------------------------- */
INSERT INTO dbo.message_call (tenant_id, messageId, [event]) VALUES
  (@t, N'MSG-0010', N'MISSED_CALL');

/* ---------------------------------------------------------------------------
   18) ENCRYPTION_PARAMS
   --------------------------------------------------------------------------- */
INSERT INTO dbo.encryptionParams (tenant_id, messageId, version, configId, timestamp, encryptedKey) VALUES
  (@t, N'MSG-0014', N'1', N'cfg-001', N'1741104900', N'b64:AbCdEf0123456789KEYsample==');

/* ---------------------------------------------------------------------------
   19) MESSAGE_FILES  (status CHECK: ok|forbidden|not_found|error|skipped)
   --------------------------------------------------------------------------- */
INSERT INTO dbo.message_files (tenant_id, messageId, file_type, original_url, file_path, downloaded_at, status) VALUES
  (@t, N'MSG-0012', N'media', N'https://storage.googleapis.com/storage.botmaker.com/GrupoRimoldi/MSG-0012/media/dano_parabrisas.jpg',
       N'files\GrupoRimoldi\MSG-0012\media\dano_parabrisas.jpg', '2025-03-04T16:25:00', N'ok'),
  (@t, N'MSG-0014', N'audio', N'https://storage.googleapis.com/storage.botmaker.com/GrupoRimoldi/MSG-0014/audio/nota.ogg',
       N'files\GrupoRimoldi\MSG-0014\audio\nota.ogg',           '2025-03-04T16:25:30', N'ok');
-- Ejemplo de archivo que falló la descarga (status != ok), file_path placeholder:
INSERT INTO dbo.message_files (tenant_id, messageId, file_type, original_url, file_path, downloaded_at, status) VALUES
  (@t, N'MSG-0012', N'audio', N'https://storage.googleapis.com/storage.botmaker.com/GrupoRimoldi/MSG-0012/audio/expirado.ogg',
       N'files\GrupoRimoldi\MSG-0012\audio\(not-downloaded)',   '2025-03-04T16:26:00', N'forbidden');

COMMIT TRAN;
GO

/* ---------------------------------------------------------------------------
   VERIFICACIÓN RÁPIDA
   --------------------------------------------------------------------------- */
SELECT 'tenants' AS tabla, COUNT(*) AS filas FROM dbo.tenants               WHERE tenant_id = N'GrupoRimoldi'
UNION ALL SELECT 'agents',                 COUNT(*) FROM dbo.agents                  WHERE tenant_id = N'GrupoRimoldi'
UNION ALL SELECT 'queues',                 COUNT(*) FROM dbo.queues                  WHERE tenant_id = N'GrupoRimoldi'
UNION ALL SELECT 'agent_performance_queues',COUNT(*) FROM dbo.agent_performance_queues WHERE tenant_id = N'GrupoRimoldi'
UNION ALL SELECT 'agent_performance',      COUNT(*) FROM dbo.agent_performance       WHERE tenant_id = N'GrupoRimoldi'
UNION ALL SELECT 'agent_metrics',          COUNT(*) FROM dbo.agent_metrics           WHERE tenant_id = N'GrupoRimoldi'
UNION ALL SELECT 'chats',                  COUNT(*) FROM dbo.chats                   WHERE tenant_id = N'GrupoRimoldi'
UNION ALL SELECT 'chat_details',           COUNT(*) FROM dbo.chat_details            WHERE tenant_id = N'GrupoRimoldi'
UNION ALL SELECT 'chat_variables',         COUNT(*) FROM dbo.chat_variables          WHERE tenant_id = N'GrupoRimoldi'
UNION ALL SELECT 'chat_tags',              COUNT(*) FROM dbo.chat_tags               WHERE tenant_id = N'GrupoRimoldi'
UNION ALL SELECT 'messages',               COUNT(*) FROM dbo.messages                WHERE tenant_id = N'GrupoRimoldi'
UNION ALL SELECT 'message_content',        COUNT(*) FROM dbo.message_content         WHERE tenant_id = N'GrupoRimoldi'
UNION ALL SELECT 'message_buttons',        COUNT(*) FROM dbo.message_buttons         WHERE tenant_id = N'GrupoRimoldi'
UNION ALL SELECT 'message_media',          COUNT(*) FROM dbo.message_media           WHERE tenant_id = N'GrupoRimoldi'
UNION ALL SELECT 'message_location',       COUNT(*) FROM dbo.message_location        WHERE tenant_id = N'GrupoRimoldi'
UNION ALL SELECT 'message_call',           COUNT(*) FROM dbo.message_call            WHERE tenant_id = N'GrupoRimoldi'
UNION ALL SELECT 'encryptionParams',       COUNT(*) FROM dbo.encryptionParams        WHERE tenant_id = N'GrupoRimoldi'
UNION ALL SELECT 'message_files',          COUNT(*) FROM dbo.message_files           WHERE tenant_id = N'GrupoRimoldi';
GO
