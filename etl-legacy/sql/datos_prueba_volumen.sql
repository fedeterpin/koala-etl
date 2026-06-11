/* ============================================================================
   DATOS DE PRUEBA - VOLUMEN (generador procedural)
   KoalaETL  |  tenant = GrupoRimoldi
   ----------------------------------------------------------------------------
   Genera cientos de chats/sesiones/mensajes con fechas distribuidas en un rango,
   para que los dashboards y el visor de chats se vean con datos realistas.

   - Ajustá @NumChats y el rango de fechas en el bloque de PARÁMETROS.
   - Respeta FKs, claves compuestas (tenant_id), columnas IDENTITY y el CHECK de status.
   - Re-ejecutable: limpia primero los datos del tenant.
   - Requiere el esquema base + el ALTER de message_files.status ya aplicados.
   ============================================================================ */

USE KoalaETL;
GO

SET NOCOUNT ON;
SET XACT_ABORT ON;

/* ----------------------------- PARÁMETROS ------------------------------- */
DECLARE @t          NVARCHAR(50) = N'GrupoRimoldi';
DECLARE @NumChats   INT          = 300;                       -- volumen de chats
DECLARE @DateStart  DATETIME2    = '2025-01-01T00:00:00';
DECLARE @DateEnd     DATETIME2   = '2025-06-30T23:59:59';
DECLARE @SpanMin    INT          = DATEDIFF(MINUTE, @DateStart, @DateEnd);

BEGIN TRAN;

/* ----------------------- LIMPIEZA (orden inverso) ----------------------- */
DELETE FROM dbo.message_files            WHERE tenant_id = @t;
DELETE FROM dbo.encryptionParams         WHERE tenant_id = @t;
DELETE FROM dbo.message_call             WHERE tenant_id = @t;
DELETE FROM dbo.message_location         WHERE tenant_id = @t;
DELETE FROM dbo.message_media            WHERE tenant_id = @t;
DELETE FROM dbo.message_carouselItems    WHERE tenant_id = @t;
DELETE FROM dbo.message_buttons          WHERE tenant_id = @t;
DELETE FROM dbo.message_content          WHERE tenant_id = @t;
DELETE FROM dbo.messages                 WHERE tenant_id = @t;
DELETE FROM dbo.chat_tags                WHERE tenant_id = @t;
DELETE FROM dbo.chat_variables           WHERE tenant_id = @t;
DELETE FROM dbo.chat_details             WHERE tenant_id = @t;
DELETE FROM dbo.agent_metrics            WHERE tenant_id = @t;
DELETE FROM dbo.agent_performance        WHERE tenant_id = @t;
DELETE FROM dbo.agent_performance_queues WHERE tenant_id = @t;
DELETE FROM dbo.chats                    WHERE tenant_id = @t;
DELETE FROM dbo.queues                   WHERE tenant_id = @t;
DELETE FROM dbo.agents                   WHERE tenant_id = @t;
DELETE FROM dbo.tenants                  WHERE tenant_id = @t;

/* ------------------------------- TENANT --------------------------------- */
INSERT INTO dbo.tenants (tenant_id, tenant_name) VALUES (@t, N'Grupo Rimoldi Seguros');

/* ------------------------------- AGENTS --------------------------------- */
DECLARE @agents TABLE (rn INT IDENTITY(1,1), agentEmail NVARCHAR(255), agentName NVARCHAR(255), agentId NVARCHAR(50), role NVARCHAR(50));
INSERT INTO @agents (agentEmail, agentName, agentId, role) VALUES
 (N'ana.gomez@gruporimoldi.com',       N'Ana Gómez',        N'AG001', N'agent'),
 (N'carlos.ruiz@gruporimoldi.com',     N'Carlos Ruiz',      N'AG002', N'agent'),
 (N'lucia.fernandez@gruporimoldi.com', N'Lucía Fernández',  N'AG003', N'supervisor'),
 (N'martin.lopez@gruporimoldi.com',    N'Martín López',     N'AG004', N'agent'),
 (N'paula.sosa@gruporimoldi.com',      N'Paula Sosa',       N'AG005', N'agent'),
 (N'diego.martinez@gruporimoldi.com',  N'Diego Martínez',   N'AG006', N'agent');

INSERT INTO dbo.agents (tenant_id, agentEmail, agentName, role)
SELECT @t, agentEmail, agentName, role FROM @agents;

DECLARE @nAgents INT = (SELECT COUNT(*) FROM @agents);

/* ------------------------------- QUEUES --------------------------------- */
DECLARE @queues TABLE (rn INT IDENTITY(1,1), queue NVARCHAR(255));
INSERT INTO @queues (queue) VALUES (N'Siniestros'), (N'Ventas'), (N'Atencion_Cliente'), (N'Postventa');
INSERT INTO dbo.queues (tenant_id, queue) SELECT @t, queue FROM @queues;
DECLARE @nQueues INT = (SELECT COUNT(*) FROM @queues);

/* ---------------- AGENT_PERFORMANCE_QUEUES (todos x todas) --------------- */
INSERT INTO dbo.agent_performance_queues (tenant_id, agentEmail, queue)
SELECT @t, a.agentEmail, q.queue FROM @agents a CROSS JOIN @queues q;

/* ------------------- AGENT_PERFORMANCE (turnos por agente) --------------- */
DECLARE @ai INT = 1;
WHILE @ai <= @nAgents
BEGIN
    DECLARE @aEmail NVARCHAR(255) = (SELECT agentEmail FROM @agents WHERE rn = @ai);
    DECLARE @d INT = 0;
    WHILE @d < 8   -- 8 turnos por agente
    BEGIN
        DECLARE @ci DATETIME2 = DATEADD(MINUTE, ABS(CHECKSUM(NEWID())) % @SpanMin, @DateStart);
        INSERT INTO dbo.agent_performance (tenant_id, agentEmail, state, checkin, checkout)
        VALUES (@t, @aEmail,
                CASE ABS(CHECKSUM(NEWID())) % 3 WHEN 0 THEN N'online' WHEN 1 THEN N'away' ELSE N'online' END,
                @ci, DATEADD(MINUTE, 420 + ABS(CHECKSUM(NEWID())) % 120, @ci));
        SET @d += 1;
    END
    SET @ai += 1;
END

/* =========================== LOOP PRINCIPAL ============================== */
DECLARE @i       INT = 1;
DECLARE @msgSeq  INT = 0;

DECLARE @tipif TABLE (rn INT IDENTITY(1,1), v NVARCHAR(100));
INSERT INTO @tipif (v) VALUES (N'Denuncia siniestro'),(N'Cotización'),(N'Consulta general'),
 (N'Siniestro granizo'),(N'Cambio de plan'),(N'Reclamo'),(N'Pago de cuota'),(N'Baja de servicio');

DECLARE @tags TABLE (rn INT IDENTITY(1,1), v NVARCHAR(100));
INSERT INTO @tags (v) VALUES (N'siniestro'),(N'urgente'),(N'cotizacion'),(N'consulta'),
 (N'granizo'),(N'mora'),(N'vip'),(N'reclamo');

DECLARE @tipos TABLE (rn INT IDENTITY(1,1), v NVARCHAR(50));
INSERT INTO @tipos (v) VALUES (N'Automotor'),(N'Hogar'),(N'Vida'),(N'Comercio');

WHILE @i <= @NumChats
BEGIN
    DECLARE @chatId NVARCHAR(50) = N'5491145' + RIGHT('500000' + CAST(@i AS NVARCHAR(10)), 6);
    DECLARE @created DATETIME2   = DATEADD(MINUTE, ABS(CHECKSUM(NEWID())) % @SpanMin, @DateStart);
    -- Índices aleatorios PRE-calculados (NEWID() dentro de una subconsulta se evalúa por fila y rompe)
    DECLARE @tipoRn  INT = ABS(CHECKSUM(NEWID())) % 4 + 1;   -- tipo_seguro
    DECLARE @tipifRn INT = ABS(CHECKSUM(NEWID())) % 8 + 1;   -- typification

    -- agente y cola aleatorios
    DECLARE @ag_rn INT = ABS(CHECKSUM(NEWID())) % @nAgents + 1;
    DECLARE @q_rn  INT = ABS(CHECKSUM(NEWID())) % @nQueues + 1;
    DECLARE @agId   NVARCHAR(50)  = (SELECT agentId   FROM @agents WHERE rn = @ag_rn);
    DECLARE @agName NVARCHAR(255) = (SELECT agentName FROM @agents WHERE rn = @ag_rn);
    DECLARE @queue  NVARCHAR(255) = (SELECT queue     FROM @queues WHERE rn = @q_rn);

    -- chats
    INSERT INTO dbo.chats (tenant_id, chatId, channelId, contactId)
    VALUES (@t, @chatId, N'whatsapp', N'+' + @chatId);

    -- chat_details
    DECLARE @isTester BIT = CASE WHEN ABS(CHECKSUM(NEWID())) % 50 = 0 THEN 1 ELSE 0 END; -- ~2% testers
    INSERT INTO dbo.chat_details
      (tenant_id, chatId, creationTime, lastSessionCreationTime, externalId, firstName, lastName,
       country, email, whatsAppWindowCloseDatetime, queueId, agentId, onHoldAgentId,
       lastUserMessageDatetime, isTester, isBotMuted, isBanned)
    VALUES
      (@t, @chatId, @created, @created,
       N'POL-' + CAST(100000 + @i AS NVARCHAR(10)),
       CASE ABS(CHECKSUM(NEWID())) % 6 WHEN 0 THEN N'Juan' WHEN 1 THEN N'María' WHEN 2 THEN N'Roberto'
                                       WHEN 3 THEN N'Sofía' WHEN 4 THEN N'Lucas' ELSE N'Carla' END,
       CASE ABS(CHECKSUM(NEWID())) % 6 WHEN 0 THEN N'Pérez' WHEN 1 THEN N'González' WHEN 2 THEN N'Díaz'
                                       WHEN 3 THEN N'Romero' WHEN 4 THEN N'Fernández' ELSE N'López' END,
       'AR', NULL, DATEADD(HOUR, 24, @created), @queue, @agId, NULL,
       DATEADD(MINUTE, 25, @created), @isTester, 0, 0);

    -- chat_variables
    INSERT INTO dbo.chat_variables (tenant_id, chatId, var_key, var_value) VALUES
      (@t, @chatId, N'nro_poliza',  N'POL-' + CAST(100000 + @i AS NVARCHAR(10))),
      (@t, @chatId, N'tipo_seguro', (SELECT v FROM @tipos WHERE rn = @tipoRn));

    -- chat_tags (1 o 2 tags, sin colisión de PK)
    INSERT INTO dbo.chat_tags (tenant_id, chatId, tag)
    SELECT @t, @chatId, x.v FROM (
        SELECT TOP (1 + ABS(CHECKSUM(NEWID())) % 2) v
        FROM @tags ORDER BY NEWID()
    ) x;

    /* ---------------------- SESIÓN + MÉTRICAS ----------------------- */
    DECLARE @sessionId NVARCHAR(150) = N'SES-' + RIGHT('000000' + CAST(@i AS NVARCHAR(10)), 6);
    DECLARE @isOpen BIT = CASE WHEN ABS(CHECKSUM(NEWID())) % 10 = 0 THEN 1 ELSE 0 END; -- ~10% abiertas
    DECLARE @att INT = 60 + ABS(CHECKSUM(NEWID())) % 900;     -- 1..16 min
    DECLARE @resp INT = 20 + ABS(CHECKSUM(NEWID())) % 120;
    DECLARE @closed DATETIME2 = CASE WHEN @isOpen = 1 THEN NULL ELSE DATEADD(SECOND, @att, @created) END;

    INSERT INTO dbo.agent_metrics
      (tenant_id, sessionId, chatId, sessionCreationTime, avgAttendingTime, avgResponseTime, queue,
       agentName, agentId, typification, closedTime, openSessions, closedSessions, onHold,
       opResponseTime, operatorResponses, sessionTransferIn, sessionTransferOut,
       sessionTransferOutNoMessages, closedWithNoMessages, timeoutNoMessages, agentTimeout,
       userTimeout, fromQueueAsignToOpAssigned, fromSessionStartToOpFirstResponse,
       fromQueueAsignToOpFirstResponse, fromOpAssignedToOpFirstResponse,
       fromQueueAsignToSessionClosed, fromOpAssignationToSessionClosed, sessionTimeout, conversationLink)
    VALUES
      (@t, @sessionId, @chatId, @created,
       CASE WHEN @isOpen = 1 THEN NULL ELSE @att END,
       CASE WHEN @isOpen = 1 THEN NULL ELSE @resp END,
       @queue, @agName, @agId,
       CASE WHEN @isOpen = 1 THEN NULL ELSE (SELECT v FROM @tipif WHERE rn = @tipifRn) END,
       @closed, @isOpen, CASE WHEN @isOpen = 1 THEN 0 ELSE 1 END,
       ABS(CHECKSUM(NEWID())) % 2,
       @resp, 2 + ABS(CHECKSUM(NEWID())) % 8,
       ABS(CHECKSUM(NEWID())) % 2, 0, 0, 0, 0, 0, 0,
       30 + ABS(CHECKSUM(NEWID())) % 60, 60 + ABS(CHECKSUM(NEWID())) % 120,
       60 + ABS(CHECKSUM(NEWID())) % 120, 30 + ABS(CHECKSUM(NEWID())) % 90,
       @att + 60, @att, 0,
       N'https://go.botmaker.com/#/chats/' + @chatId);

    /* -------------------------- MENSAJES ---------------------------- */
    DECLARE @nMsgs INT = 2 + ABS(CHECKSUM(NEWID())) % 6;   -- 2..7 mensajes
    DECLARE @k INT = 0;
    WHILE @k < @nMsgs
    BEGIN
        SET @msgSeq += 1;
        DECLARE @mid NVARCHAR(50) = N'MSG-' + RIGHT('00000000' + CAST(@msgSeq AS NVARCHAR(10)), 8);
        DECLARE @mTime DATETIME2 = DATEADD(MINUTE, @k * (1 + ABS(CHECKSUM(NEWID())) % 4), @created);

        -- alterna user / bot / agent
        DECLARE @from NVARCHAR(50) = CASE @k % 3 WHEN 0 THEN N'user' WHEN 1 THEN N'bot' ELSE N'agent' END;
        DECLARE @mAgId NVARCHAR(50) = CASE WHEN @from = N'agent' THEN @agId ELSE NULL END;

        INSERT INTO dbo.messages
          (tenant_id, id, creationTime, [from], agentId, queueId, sessionCreationTime, chatId, sessionId, whatsAppTemplateName)
        VALUES (@t, @mid, @mTime, @from, @mAgId, @queue, @created, @chatId, @sessionId,
                CASE WHEN @from = N'bot' AND @k = 1 THEN N'menu_bienvenida' ELSE NULL END);

        -- ¿adjunto? ~15% imagen, ~10% audio, resto texto (solo en mensajes del usuario)
        DECLARE @rndAtt INT = ABS(CHECKSUM(NEWID())) % 100;
        DECLARE @ctype NVARCHAR(50) =
            CASE WHEN @from = N'user' AND @rndAtt < 15 THEN N'image'
                 WHEN @from = N'user' AND @rndAtt < 25 THEN N'audio'
                 ELSE N'text' END;

        DECLARE @audioUrl NVARCHAR(MAX) =
            CASE WHEN @ctype = N'audio'
                 THEN N'https://storage.googleapis.com/storage.botmaker.com/' + @t + N'/' + @mid + N'/audio/nota.ogg'
                 ELSE NULL END;

        INSERT INTO dbo.message_content (tenant_id, messageId, [type], text, selectedButton, originalText, originalAudioUrl)
        VALUES (@t, @mid, @ctype,
                CASE @ctype
                    WHEN N'image' THEN N'Foto adjunta'
                    WHEN N'audio' THEN NULL
                    ELSE CASE @from WHEN N'user' THEN N'Consulta del cliente sobre su póliza'
                                    WHEN N'bot'  THEN N'¡Hola! ¿En qué puedo ayudarte?'
                                    ELSE N'Te ayudo con eso, dame un momento.' END
                END,
                NULL, CASE WHEN @ctype = N'audio' THEN N'Audio del cliente' ELSE NULL END, @audioUrl);

        -- imagen -> message_media + message_files(media)
        IF @ctype = N'image'
        BEGIN
            DECLARE @urlImg NVARCHAR(MAX) = N'https://storage.googleapis.com/storage.botmaker.com/' + @t + N'/' + @mid + N'/media/foto.jpg';
            INSERT INTO dbo.message_media (tenant_id, messageId, caption, url) VALUES (@t, @mid, N'Foto adjunta', @urlImg);

            DECLARE @stImg INT = ABS(CHECKSUM(NEWID())) % 100;
            DECLARE @statusImg NVARCHAR(20) = CASE WHEN @stImg < 85 THEN N'ok' WHEN @stImg < 92 THEN N'forbidden'
                                                   WHEN @stImg < 96 THEN N'not_found' ELSE N'error' END;
            INSERT INTO dbo.message_files (tenant_id, messageId, file_type, original_url, file_path, downloaded_at, status)
            VALUES (@t, @mid, N'media', @urlImg,
                    CASE WHEN @statusImg = N'ok'
                         THEN N'files\' + @t + N'\' + @mid + N'\media\foto.jpg'
                         ELSE N'files\' + @t + N'\' + @mid + N'\media\(not-downloaded)' END,
                    DATEADD(MINUTE, 5, @mTime), @statusImg);
        END

        -- audio -> message_files(audio) (+ encryptionParams a veces)
        IF @ctype = N'audio'
        BEGIN
            DECLARE @stAud INT = ABS(CHECKSUM(NEWID())) % 100;
            DECLARE @statusAud NVARCHAR(20) = CASE WHEN @stAud < 85 THEN N'ok' WHEN @stAud < 92 THEN N'forbidden'
                                                   WHEN @stAud < 96 THEN N'not_found' ELSE N'error' END;
            INSERT INTO dbo.message_files (tenant_id, messageId, file_type, original_url, file_path, downloaded_at, status)
            VALUES (@t, @mid, N'audio', @audioUrl,
                    CASE WHEN @statusAud = N'ok'
                         THEN N'files\' + @t + N'\' + @mid + N'\audio\nota.ogg'
                         ELSE N'files\' + @t + N'\' + @mid + N'\audio\(not-downloaded)' END,
                    DATEADD(MINUTE, 5, @mTime), @statusAud);

            IF ABS(CHECKSUM(NEWID())) % 2 = 0
                INSERT INTO dbo.encryptionParams (tenant_id, messageId, version, configId, timestamp, encryptedKey)
                VALUES (@t, @mid, N'1', N'cfg-001', CAST(DATEDIFF(SECOND, '2025-01-01', @mTime) AS NVARCHAR(50)), N'b64:KEYsample==');
        END
        SET @k += 1;
    END

    SET @i += 1;
END

COMMIT TRAN;
GO

/* ----------------------------- VERIFICACIÓN ----------------------------- */
SELECT 'agents' AS tabla, COUNT(*) AS filas FROM dbo.agents WHERE tenant_id = N'GrupoRimoldi'
UNION ALL SELECT 'queues',          COUNT(*) FROM dbo.queues          WHERE tenant_id = N'GrupoRimoldi'
UNION ALL SELECT 'chats',           COUNT(*) FROM dbo.chats           WHERE tenant_id = N'GrupoRimoldi'
UNION ALL SELECT 'chat_details',    COUNT(*) FROM dbo.chat_details    WHERE tenant_id = N'GrupoRimoldi'
UNION ALL SELECT 'agent_metrics',   COUNT(*) FROM dbo.agent_metrics   WHERE tenant_id = N'GrupoRimoldi'
UNION ALL SELECT 'messages',        COUNT(*) FROM dbo.messages        WHERE tenant_id = N'GrupoRimoldi'
UNION ALL SELECT 'message_content', COUNT(*) FROM dbo.message_content WHERE tenant_id = N'GrupoRimoldi'
UNION ALL SELECT 'message_media',   COUNT(*) FROM dbo.message_media   WHERE tenant_id = N'GrupoRimoldi'
UNION ALL SELECT 'message_files',   COUNT(*) FROM dbo.message_files   WHERE tenant_id = N'GrupoRimoldi';
GO
