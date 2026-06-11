# scripts/etl_botmaker_upd_chat.py

import sys
import os
from pathlib import Path

# 1) Path del directorio raíz del proyecto (que contiene etl_botmaker_logs.py)
ROOT = Path(__file__).resolve().parent.parent  # ajusta si hace falta
sys.path.insert(0, str(ROOT))

# 2) importamos módulo principal
from etl_botmaker_logs import (
    get_connection,
    api_request,
    URL_CHAT,
    TENANT_ID,
    logger,
)

import pyodbc
import logging
from pathlib import Path
from dotenv import load_dotenv

def etl_chats_only(cur: pyodbc.Cursor) -> None:
    """
    Actualiza sólo dbo.chats llamando a GET /chats/{chatId}
    para que channelId y contactId queden siempre correctos.
    """
    logger.info("▶ ETL solo dbo.chats: refrescar channelId y contactId")

    # 1) Obtenemos todos los chatId existentes
    cur.execute("SELECT chatId FROM dbo.chats WHERE tenant_id = ?", TENANT_ID)
    chat_ids = [row.chatId for row in cur.fetchall()]

    count = 0
    for cid in chat_ids:
        # 2) Llamada al endpoint de chat
        resp = api_request("GET", URL_CHAT.format(cid))
        chat = resp.json().get("chat", {}) or {}
        chan    = chat.get("channelId")
        contact = chat.get("contactId")

        # 3) MERGE para sólo actualizar esos dos campos
        cur.execute("""
            MERGE dbo.chats AS target
            USING (VALUES(?, ?, ?, ?)) AS src(tenant_id, chatId, channelId, contactId)
              ON target.tenant_id = src.tenant_id
             AND target.chatId    = src.chatId
            WHEN MATCHED THEN
              UPDATE SET
                channelId = src.channelId,
                contactId = src.contactId;
        """,
        TENANT_ID, cid, chan, contact
        )
        count += 1

    cur.commit()
    logger.info("✔ dbo.chats actualizados: %d filas", count)

def main():
    # carga tu .env si lo necesitas
    BASE_DIR = Path(__file__).resolve().parent.parent
    load_dotenv(BASE_DIR / "config" / ".env")

    conn = get_connection()
    cur  = conn.cursor()
    try:
        etl_chats_only(cur)
    except Exception:
        logger.exception("Error actualizando dbo.chats")
        conn.rollback()
    finally:
        conn.close()

if __name__ == "__main__":
    main()