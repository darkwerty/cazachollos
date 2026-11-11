"""Web accounts (Google) and the Telegram chat where each one gets its alerts.

Linking: the web asks for a one-time code (15 minutes) and opens https://t.me/<bot>?start=<code>; Telegram sends
"/start <code>" to the bot, which ties that chat to the account. A chat belongs to one account at most.
"""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta

from sqlalchemy import text

from src.infrastructure.db.session import AsyncSessionLocal

LINK_TTL = timedelta(minutes=15)


class AccountStore:
    async def upsert(self, user_id: str, email: str | None, name: str | None) -> dict:
        async with AsyncSessionLocal() as session:
            row = (
                await session.execute(
                    text(
                        "INSERT INTO users (id, email, name) VALUES (:id, :email, :name) "
                        "ON CONFLICT (id) DO UPDATE SET email = EXCLUDED.email, name = EXCLUDED.name "
                        "RETURNING id, email, name, telegram_chat_id"
                    ),
                    {"id": user_id, "email": email, "name": name},
                )
            ).one()
            await session.commit()
            return dict(row._mapping)

    async def new_link_code(self, user_id: str) -> str:
        code = secrets.token_hex(12)
        async with AsyncSessionLocal() as session:
            await session.execute(
                text("DELETE FROM telegram_links WHERE expires_at < :now"), {"now": datetime.utcnow()}
            )
            await session.execute(
                text("INSERT INTO telegram_links (code, user_id, expires_at) VALUES (:c, :u, :e)"),
                {"c": code, "u": user_id, "e": datetime.utcnow() + LINK_TTL},
            )
            await session.commit()
        return code

    async def link(self, code: str, chat_id: int) -> str | None:
        """Ties the chat to the account of the code. Email (or name) of the account, or None if the code is not valid."""
        async with AsyncSessionLocal() as session:
            row = (
                await session.execute(
                    text("DELETE FROM telegram_links WHERE code = :c AND expires_at >= :now RETURNING user_id"),
                    {"c": code, "now": datetime.utcnow()},
                )
            ).first()
            if row is None:
                await session.commit()
                return None
            await session.execute(
                text("UPDATE users SET telegram_chat_id = NULL WHERE telegram_chat_id = :chat"), {"chat": chat_id}
            )
            user = (
                await session.execute(
                    text("UPDATE users SET telegram_chat_id = :chat WHERE id = :u RETURNING email, name"),
                    {"chat": chat_id, "u": row.user_id},
                )
            ).first()
            await session.commit()
            return (user.email or user.name or "tu cuenta") if user else None

    async def unlink(self, user_id: str) -> None:
        async with AsyncSessionLocal() as session:
            await session.execute(text("UPDATE users SET telegram_chat_id = NULL WHERE id = :u"), {"u": user_id})
            await session.commit()
