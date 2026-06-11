SELECT
    c.tenant_id AS tenantId,
    c.chatId,
    c.contactId,
    ud.email,
    ud.externalId,
    ud.firstName,
    ud.lastName,
    ud.phone_from_chat,
    ud.phone_from_vars,
    m.id AS messageId,
    m.creationTime AS messageTime,
    m.[from] AS messageFrom,
	mc.type AS contentType,
    mc.text AS contentText,
    m.agentId,
    m.queueId,
    m.sessionCreationTime,
    m.sessionId,
    mc.selectedButton AS contentSelectedButton,
    mc.originalText AS contentOriginalText,
    mc.originalAudioUrl AS contentOriginalAudioUrl,
    btn.button AS buttonLabel,
    carr.carouselItem,
    mm.caption AS mediaCaption,
    mm.url AS mediaUrl,
    mf.file_type AS fileType,
    mf.original_url AS fileOriginalUrl,
    mf.file_path AS fileRelativePath,
    mf.downloaded_at AS fileDownloadedAt,
    ml.latitude AS locationLatitude,
    ml.longitude AS locationLongitude,
    ml.name AS locationName,
    ml.address AS locationAddress,
    call.event AS callEvent,
    ep.version AS encryptVersion,
    ep.configId AS encryptConfigId,
    ep.timestamp AS encryptTimestamp,
    ep.encryptedKey AS encryptKey
FROM dbo.chats AS c
LEFT OUTER JOIN dbo.vw_ChatUserData AS ud
    ON ud.tenant_id = c.tenant_id AND ud.chatId = c.chatId
INNER JOIN dbo.messages AS m
    ON c.tenant_id = m.tenant_id AND c.chatId = m.chatId
LEFT OUTER JOIN dbo.message_content AS mc
    ON mc.tenant_id = m.tenant_id AND mc.messageId = m.id
LEFT OUTER JOIN dbo.message_buttons AS btn
    ON btn.tenant_id = m.tenant_id AND btn.messageId = m.id
LEFT OUTER JOIN dbo.message_carouselItems AS carr
    ON carr.tenant_id = m.tenant_id AND carr.messageId = m.id
LEFT OUTER JOIN dbo.message_media AS mm
    ON mm.tenant_id = m.tenant_id AND mm.messageId = m.id
LEFT OUTER JOIN dbo.message_files AS mf
    ON mf.tenant_id = m.tenant_id AND mf.messageId = m.id
LEFT OUTER JOIN dbo.message_location AS ml
    ON ml.tenant_id = m.tenant_id AND ml.messageId = m.id
LEFT OUTER JOIN dbo.message_call AS call
    ON call.tenant_id = m.tenant_id AND call.messageId = m.id
LEFT OUTER JOIN dbo.encryptionParams AS ep
    ON ep.tenant_id = m.tenant_id AND ep.messageId = m.id
WHERE c.tenant_id = 'mlasegurosconexpertos'
and   c.contactId = '34666213350'
ORDER BY m.creationTime
