-- ======================================================
-- Limpieza ordenada de KOALA-ETL sin deshabilitar FKs
-- Se usan DELETE en orden “hijo ? padre” y luego DBCC CHECKIDENT
-- ======================================================

USE [KoalaETL];
PRINT 'Comenzando limpieza de tablas en orden...';

------------------------------------------------------------------------
-- 1) Borrar tablas hijas absolutas
------------------------------------------------------------------------
DELETE FROM dbo.message_buttons;
DELETE FROM dbo.message_carouselItems;
DELETE FROM dbo.message_media;
DELETE FROM dbo.message_files;
DELETE FROM dbo.message_location;
DELETE FROM dbo.message_call;
DELETE FROM dbo.message_content;
DELETE FROM dbo.encryptionParams;

DELETE FROM dbo.chat_variables;
DELETE FROM dbo.chat_tags;

DELETE FROM dbo.agent_performance_queues;

PRINT '? Tablas hijas absolutas borradas.';

------------------------------------------------------------------------
-- 2) Borrar tablas intermedias
------------------------------------------------------------------------
DELETE FROM dbo.messages;
DELETE FROM dbo.chat_details;
DELETE FROM dbo.agent_performance;
DELETE FROM dbo.agent_metrics;

PRINT '? Tablas intermedias borradas.';

------------------------------------------------------------------------
-- 3) Borrar tablas raíz de submodelos / lookup
------------------------------------------------------------------------
DELETE FROM dbo.chats;
DELETE FROM dbo.agents;
DELETE FROM dbo.queues;

PRINT '? Tablas de lookup / padres borradas.';

DELETE FROM dbo.etl_control;