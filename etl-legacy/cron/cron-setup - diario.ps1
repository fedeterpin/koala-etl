# Diario
schtasks /Create `
    /SC DAILY `
    /TN "KOALA-ETL Diario" `
    /TR "'C:\KoalaETL\venv\Scripts\python.exe' 'C:\KoalaETL\scripts\etl_botmaker_logs.py' >> 'C:\KoalaETL\logs\koala_etl_cron.log' 2>&1" `
    /ST 23:30 `
    /RL HIGHEST `
    /F

