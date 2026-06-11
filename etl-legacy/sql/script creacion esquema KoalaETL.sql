-- 0) Crear DB si no existe y usarla
IF DB_ID(N'KoalaETL') IS NULL
BEGIN
    CREATE DATABASE KoalaETL;
END;

BEGIN

USE KoalaETL;

-- 1) Tenants
CREATE TABLE tenants (
    tenant_id   NVARCHAR(50) PRIMARY KEY,
    tenant_name NVARCHAR(255) NOT NULL
);

-- 2) Agents
CREATE TABLE agents (
    tenant_id   NVARCHAR(50) NOT NULL,
    agentEmail  NVARCHAR(255) NOT NULL,
    agentName   NVARCHAR(255) NOT NULL,
    role        NVARCHAR(50)  NOT NULL,
    CONSTRAINT PK_agents           PRIMARY KEY (tenant_id, agentEmail),
    CONSTRAINT FK_agents_tenant    FOREIGN KEY (tenant_id) REFERENCES tenants (tenant_id)
);

-- 3) Queues
CREATE TABLE queues (
    tenant_id   NVARCHAR(50) NOT NULL,
    queue       NVARCHAR(255) NOT NULL,
    CONSTRAINT PK_queues           PRIMARY KEY (tenant_id, queue),
    CONSTRAINT FK_queues_tenant    FOREIGN KEY (tenant_id) REFERENCES tenants (tenant_id)
);

-- 4) Agent Performance M–N Queues
CREATE TABLE agent_performance_queues (
    tenant_id   NVARCHAR(50) NOT NULL,
    agentEmail  NVARCHAR(255) NOT NULL,
    queue       NVARCHAR(255) NOT NULL,
    CONSTRAINT PK_apq               PRIMARY KEY (tenant_id, agentEmail, queue),
    CONSTRAINT FK_apq_tenant        FOREIGN KEY (tenant_id)             REFERENCES tenants    (tenant_id),
    CONSTRAINT FK_apq_agent         FOREIGN KEY (tenant_id, agentEmail)  REFERENCES agents     (tenant_id, agentEmail),
    CONSTRAINT FK_apq_queue         FOREIGN KEY (tenant_id, queue)       REFERENCES queues     (tenant_id, queue)
);

-- 5) Agent Performance
CREATE TABLE agent_performance (
    tenant_id     NVARCHAR(50) NOT NULL,
    performanceId INT IDENTITY(1,1) NOT NULL,
    agentEmail    NVARCHAR(255) NOT NULL,
    state         NVARCHAR(50)  NULL,
    checkin       DATETIME2      NULL,
    checkout      DATETIME2      NULL,
    CONSTRAINT PK_perf             PRIMARY KEY (tenant_id, performanceId),
    CONSTRAINT FK_perf_tenant      FOREIGN KEY (tenant_id)            REFERENCES tenants (tenant_id),
    CONSTRAINT FK_perf_agent       FOREIGN KEY (tenant_id, agentEmail) REFERENCES agents  (tenant_id, agentEmail)
);

-- 6) Agent Metrics
CREATE TABLE agent_metrics (
    tenant_id                           NVARCHAR(50)   NOT NULL,
    sessionId                           NVARCHAR(150)  NOT NULL,
    chatId                              NVARCHAR(50)   NULL,
    sessionCreationTime                 DATETIME2      NULL,
    avgAttendingTime                    INT            NULL,
    avgResponseTime                     INT            NULL,
    queue                               NVARCHAR(255)  NULL,
    agentName                           NVARCHAR(255)  NULL,
    agentId                             NVARCHAR(50)   NULL,
    typification                        NVARCHAR(255)  NULL,
    closedTime                          DATETIME2      NULL,
    openSessions                        INT            NULL,
    closedSessions                      INT            NULL,
    onHold                              INT            NULL,
    opResponseTime                      INT            NULL,
    operatorResponses                   INT            NULL,
    sessionTransferIn                   INT            NULL,
    sessionTransferOut                  INT            NULL,
    sessionTransferOutNoMessages        INT            NULL,
    closedWithNoMessages                INT            NULL,
    timeoutNoMessages                   INT            NULL,
    agentTimeout                        INT            NULL,
    userTimeout                         INT            NULL,
    fromQueueAsignToOpAssigned          INT            NULL,
    fromSessionStartToOpFirstResponse   INT            NULL,
    fromQueueAsignToOpFirstResponse     INT            NULL,
    fromOpAssignedToOpFirstResponse     INT            NULL,
    fromQueueAsignToSessionClosed       INT            NULL,
    fromOpAssignationToSessionClosed    INT            NULL,
    sessionTimeout                      INT            NULL,
    conversationLink                    NVARCHAR(MAX)  NULL,
    CONSTRAINT PK_metrics                 PRIMARY KEY (tenant_id, sessionId),
    CONSTRAINT FK_metrics_tenant          FOREIGN KEY (tenant_id)       REFERENCES tenants (tenant_id),
    CONSTRAINT FK_metrics_queue           FOREIGN KEY (tenant_id, queue) REFERENCES queues (tenant_id, queue)
);

-- 7) Chats
CREATE TABLE chats (
    tenant_id  NVARCHAR(50) NOT NULL,
    chatId     NVARCHAR(50) NOT NULL,
    channelId  NVARCHAR(255) NULL,
    contactId  NVARCHAR(255) NULL,
    CONSTRAINT PK_chats           PRIMARY KEY (tenant_id, chatId),
    CONSTRAINT FK_chats_tenant    FOREIGN KEY (tenant_id)          REFERENCES tenants (tenant_id)
);

-- 8) Chat Details
CREATE TABLE chat_details (
    tenant_id                   NVARCHAR(50)   NOT NULL,
    chatId                      NVARCHAR(50)   NOT NULL,
    creationTime                DATETIME2      NULL,
    lastSessionCreationTime     DATETIME2      NULL,
    externalId                  NVARCHAR(100)  NULL,
    firstName                   NVARCHAR(100)  NULL,
    lastName                    NVARCHAR(100)  NULL,
    country                     CHAR(2)        NULL,
    email                       NVARCHAR(255)  NULL,
    whatsAppWindowCloseDatetime DATETIME2      NULL,
    queueId                     NVARCHAR(255)  NULL,
    agentId                     NVARCHAR(50)   NULL,
    onHoldAgentId               NVARCHAR(50)   NULL,
    lastUserMessageDatetime     DATETIME2      NULL,
    isTester                    BIT            NULL,
    isBotMuted                  BIT            NULL,
    isBanned                    BIT            NULL,
    CONSTRAINT PK_chat_details             PRIMARY KEY (tenant_id, chatId),
    CONSTRAINT FK_chat_details_chats       FOREIGN KEY (tenant_id, chatId) REFERENCES chats (tenant_id, chatId)
);

-- 9) Chat Variables
CREATE TABLE chat_variables (
    tenant_id NVARCHAR(50)  NOT NULL,
    chatId    NVARCHAR(50)  NOT NULL,
    var_key   NVARCHAR(100) NOT NULL,
    var_value NVARCHAR(MAX) NULL,
    CONSTRAINT PK_chat_variables        PRIMARY KEY (tenant_id, chatId, var_key),
    CONSTRAINT FK_chat_variables_chat   FOREIGN KEY (tenant_id, chatId) REFERENCES chats (tenant_id, chatId)
);

-- 10) Chat Tags
CREATE TABLE chat_tags (
    tenant_id NVARCHAR(50)  NOT NULL,
    chatId    NVARCHAR(50)  NOT NULL,
    tag       NVARCHAR(100) NOT NULL,
    CONSTRAINT PK_chat_tags         PRIMARY KEY (tenant_id, chatId, tag),
    CONSTRAINT FK_chat_tags_chat    FOREIGN KEY (tenant_id, chatId) REFERENCES chats (tenant_id, chatId)
);

-- 11) Messages
CREATE TABLE messages (
    tenant_id            NVARCHAR(50)   NOT NULL,
    id                   NVARCHAR(50)   NOT NULL,
    creationTime         DATETIME2      NULL,
    [from]               NVARCHAR(50)   NULL,
    agentId              NVARCHAR(50)   NULL,
    queueId              NVARCHAR(255)  NULL,
    sessionCreationTime  DATETIME2      NULL,
    chatId               NVARCHAR(50)   NULL,
    sessionId            NVARCHAR(150)  NULL,
    whatsAppTemplateName NVARCHAR(255)  NULL,
    CONSTRAINT PK_msgs               PRIMARY KEY (tenant_id, id),
    CONSTRAINT FK_msgs_tenant        FOREIGN KEY (tenant_id)                 REFERENCES tenants (tenant_id),
    CONSTRAINT FK_msgs_chat          FOREIGN KEY (tenant_id, chatId)          REFERENCES chats    (tenant_id, chatId),
    CONSTRAINT FK_msgs_queue         FOREIGN KEY (tenant_id, queueId)         REFERENCES queues   (tenant_id, queue)
);

-- 12) Message Content
CREATE TABLE message_content (
    tenant_id    NVARCHAR(50)  NOT NULL,
    messageId    NVARCHAR(50)  NOT NULL,
    [type]       NVARCHAR(50)  NULL,
    text         NVARCHAR(MAX) NULL,
    selectedButton NVARCHAR(255) NULL,
    originalText NVARCHAR(MAX) NULL,
    originalAudioUrl NVARCHAR(MAX) NULL,
    CONSTRAINT PK_mcontent              PRIMARY KEY (tenant_id, messageId),
    CONSTRAINT FK_mcontent_tenant       FOREIGN KEY (tenant_id)          REFERENCES tenants  (tenant_id),
    CONSTRAINT FK_mcontent_msg          FOREIGN KEY (tenant_id, messageId) REFERENCES messages (tenant_id, id)
);

-- 13) Message Buttons
CREATE TABLE message_buttons (
    tenant_id NVARCHAR(50)  NOT NULL,
    messageId NVARCHAR(50)  NOT NULL,
    button    NVARCHAR(255) NOT NULL,
    CONSTRAINT PK_mbuttons            PRIMARY KEY (tenant_id, messageId, button),
    CONSTRAINT FK_mbuttons_tenant     FOREIGN KEY (tenant_id)          REFERENCES tenants  (tenant_id),
    CONSTRAINT FK_mbuttons_msg        FOREIGN KEY (tenant_id, messageId) REFERENCES messages (tenant_id, id)
);

-- 14) Carousel Items
CREATE TABLE message_carouselItems (
  tenant_id     NVARCHAR(50) NOT NULL,
  messageId     NVARCHAR(50) NOT NULL,
  itemIndex     INT IDENTITY(1,1) NOT NULL,
  carouselItem  NVARCHAR(MAX)   NULL,
  CONSTRAINT PK_mcarousel PRIMARY KEY (tenant_id, messageId, itemIndex),
  CONSTRAINT FK_mcarousel_tenant FOREIGN KEY (tenant_id) REFERENCES tenants(tenant_id),
  CONSTRAINT FK_mcarousel_msg    FOREIGN KEY (tenant_id, messageId) REFERENCES messages(tenant_id, id)
);

-- 15) Media
CREATE TABLE message_media (
    tenant_id NVARCHAR(50) NOT NULL,
    mediaId   INT IDENTITY(1,1) NOT NULL,
    messageId NVARCHAR(50) NOT NULL,
    caption    NVARCHAR(MAX) NULL,
    url        NVARCHAR(MAX) NULL,
    CONSTRAINT PK_mmedia             PRIMARY KEY (tenant_id, mediaId),
    CONSTRAINT FK_mmedia_tenant      FOREIGN KEY (tenant_id)           REFERENCES tenants  (tenant_id),
    CONSTRAINT FK_mmedia_msg         FOREIGN KEY (tenant_id, messageId) REFERENCES messages (tenant_id, id)
);

-- 16) Location
CREATE TABLE message_location (
    tenant_id NVARCHAR(50) NOT NULL,
    messageId NVARCHAR(50) NOT NULL,
    latitude   NVARCHAR(50)  NULL,
    longitude  NVARCHAR(50)  NULL,
    name       NVARCHAR(255) NULL,
    address    NVARCHAR(MAX) NULL,
    CONSTRAINT PK_mlocation           PRIMARY KEY (tenant_id, messageId),
    CONSTRAINT FK_mlocation_tenant    FOREIGN KEY (tenant_id)             REFERENCES tenants  (tenant_id),
    CONSTRAINT FK_mlocation_msg       FOREIGN KEY (tenant_id, messageId)   REFERENCES messages (tenant_id, id)
);

-- 17) Call Event
CREATE TABLE message_call (
    tenant_id NVARCHAR(50) NOT NULL,
    messageId NVARCHAR(50) NOT NULL,
    [event]    NVARCHAR(50)  NULL,
    CONSTRAINT PK_mcall              PRIMARY KEY (tenant_id, messageId),
    CONSTRAINT FK_mcall_tenant       FOREIGN KEY (tenant_id)             REFERENCES tenants  (tenant_id),
    CONSTRAINT FK_mcall_msg          FOREIGN KEY (tenant_id, messageId)   REFERENCES messages (tenant_id, id)
);

-- 18) Encryption Params
CREATE TABLE encryptionParams (
    tenant_id    NVARCHAR(50) NOT NULL,
    messageId    NVARCHAR(50) NOT NULL,
    version      NVARCHAR(50) NULL,
    configId     NVARCHAR(50) NULL,
    timestamp    NVARCHAR(50) NULL,
    encryptedKey NVARCHAR(MAX) NULL,
    CONSTRAINT PK_enc               PRIMARY KEY (tenant_id, messageId),
    CONSTRAINT FK_enc_tenant        FOREIGN KEY (tenant_id)             REFERENCES tenants (tenant_id),
    CONSTRAINT FK_enc_msg           FOREIGN KEY (tenant_id, messageId)   REFERENCES messages (tenant_id, id)
);

-- 19) Archivar Media/Audio
CREATE TABLE message_files (
    tenant_id     NVARCHAR(50) NOT NULL,
    messageId     NVARCHAR(50) NOT NULL,
    file_type     NVARCHAR(20)  NOT NULL,  -- 'media'| 'audio'
    original_url  NVARCHAR(500) NOT NULL,
    file_path     NVARCHAR(500) NOT NULL,
    downloaded_at DATETIME2      NOT NULL,
    CONSTRAINT PK_message_files           PRIMARY KEY (tenant_id, messageId, file_type),
    CONSTRAINT FK_msg_files_msg           FOREIGN KEY (tenant_id, messageId) REFERENCES messages (tenant_id, id)
);

END;
