SELECT 
    c.[contactId], 
    c.[chatId], 
    c.[tenant_id], 
    m.[id] AS message_id,
    m.[from], 
    mc.[type] AS estado_mensaje,
    mc.[text] AS texto_mensaje,
    m.[creationTime], 
    m.[sessionId], 
    mc.[selectedButton] AS boton_seleccionado,
    mc.[originalText] AS texto_original,
    mc.[originalAudioUrl] AS url_audio_original
FROM 
    [KoalaETL].[dbo].[chats] c
JOIN 
    [KoalaETL].[dbo].[messages] m ON c.[chatId] = m.[chatId] AND c.[tenant_id] = m.[tenant_id]
LEFT JOIN 
    [KoalaETL].[dbo].[message_content] mc ON m.[id] = mc.[messageId] AND m.[tenant_id] = mc.[tenant_id]
WHERE 
    c.[contactId] = '34666213350'
ORDER BY 
    m.[creationTime]


/*SELECT [tenant_id]
      ,[chatId]
      ,[channelId]
      ,[contactId]
  FROM [KoalaETL].[dbo].[chats]
  where [chatId] = 'RKDFZGYWRMIYAHHI72VQ'
  and   [contactId] like '34666213350'*/