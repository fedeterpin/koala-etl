SELECT tenant_id, messageId, file_type, original_url, file_path, status, downloaded_at
FROM dbo.message_files
WHERE status <> 'downloaded' OR file_path LIKE '%(not-downloaded)%';