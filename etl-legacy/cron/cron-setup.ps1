# Día 1
schtasks /Create `
    /SC MONTHLY `
    /D 1 `
    /TN "KOALA-ETL Quincenal Dia 1" `
    /TR "`"C:\KoalaETL\venv\Scripts\python.exe`" `"C:\KoalaETL\scripts\etl_botmaker_logs.py`" >> `"C:\KoalaETL\logs\koala_etl_cron.log`" 2>&1" `
    /ST 23:00 `
    /RL HIGHEST `
    /F

# Día 16
schtasks /Create `
    /SC MONTHLY `
    /D 16 `
    /TN "KOALA-ETL Quincenal Dia 16" `
    /TR "`"C:\KoalaETL\venv\Scripts\python.exe`" `"C:\KoalaETL\scripts\etl_botmaker_logs.py`" >> `"C:\KoalaETL\logs\koala_etl_cron.log`" 2>&1" `
    /ST 23:00 `
    /RL HIGHEST `
    /F