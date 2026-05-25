import json
import logging
import os
from datetime import date, datetime, timedelta, timezone
from typing import Any
from uuid import UUID, uuid4

import asyncpg


logger = logging.getLogger("control-castora.database")

pool: asyncpg.Pool | None = None


async def init_db() -> None:
    global pool

    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        logger.warning("DATABASE_URL no configurada; funciones de cuentos desactivadas")
        return

    pool = await asyncpg.create_pool(database_url, min_size=1, max_size=5)
    await migrate()


async def close_db() -> None:
    global pool

    if pool:
        await pool.close()
        pool = None


def db_available() -> bool:
    return pool is not None


def require_pool() -> asyncpg.Pool:
    if not pool:
        raise RuntimeError("DATABASE_URL no configurada o base de datos no inicializada")
    return pool


async def migrate() -> None:
    db = require_pool()
    async with db.acquire() as conn:
        await conn.execute(
            """
            create table if not exists users (
                telegram_user_id bigint primary key,
                name text,
                role text not null default 'other',
                created_at timestamptz not null default now()
            );

            create table if not exists stories (
                id bigserial primary key,
                title text not null,
                full_text text not null,
                summary text not null,
                status text not null default 'pending',
                narrator text not null,
                selected_option text,
                offered_options jsonb,
                characters_used jsonb,
                locations_used jsonb,
                new_lore_proposals jsonb,
                delivered_to_user_id bigint references users(telegram_user_id),
                created_at timestamptz not null default now(),
                delivered_at timestamptz
            );

            create table if not exists daily_limits (
                telegram_user_id bigint references users(telegram_user_id),
                date date not null,
                story_id bigint references stories(id),
                consumed_at timestamptz not null default now(),
                primary key (telegram_user_id, date)
            );

            create table if not exists story_offers (
                id uuid primary key,
                telegram_user_id bigint references users(telegram_user_id),
                narrator text not null,
                options jsonb not null,
                created_at timestamptz not null default now(),
                expires_at timestamptz not null,
                consumed_at timestamptz
            );

            create table if not exists auto_reply_drafts (
                id bigserial primary key,
                animal_key text not null,
                incoming_chat_id bigint not null,
                incoming_text text not null,
                proposed_text text not null,
                status text not null default 'pending',
                reason text,
                created_at timestamptz not null default now(),
                reviewed_at timestamptz,
                sent_at timestamptz,
                admin_user_id bigint
            );
            """
        )


async def upsert_user(telegram_user_id: int, name: str | None, role: str = "other") -> None:
    db = require_pool()
    await db.execute(
        """
        insert into users (telegram_user_id, name, role)
        values ($1, $2, $3)
        on conflict (telegram_user_id) do update
        set name = coalesce(excluded.name, users.name),
            role = case
                when users.role in ('admin', 'sandra') then users.role
                else excluded.role
            end
        """,
        telegram_user_id,
        name,
        role,
    )


async def daily_story_consumed(telegram_user_id: int, story_date: date) -> bool:
    db = require_pool()
    value = await db.fetchval(
        """
        select exists(
            select 1 from daily_limits
            where telegram_user_id = $1 and date = $2
        )
        """,
        telegram_user_id,
        story_date,
    )
    return bool(value)


async def create_story_offer(
    telegram_user_id: int,
    narrator: str,
    options: list[dict[str, Any]],
) -> str:
    db = require_pool()
    offer_id = uuid4()
    async with db.acquire() as conn:
        async with conn.transaction():
            await conn.execute(
                """
                update story_offers
                set expires_at = now()
                where telegram_user_id = $1
                  and consumed_at is null
                  and expires_at > now()
                """,
                telegram_user_id,
            )
            await conn.execute(
                """
                insert into story_offers (id, telegram_user_id, narrator, options, expires_at)
                values ($1, $2, $3, $4::jsonb, $5)
                """,
                offer_id,
                telegram_user_id,
                narrator,
                json.dumps(options, ensure_ascii=False),
                datetime.now(timezone.utc) + timedelta(hours=6),
            )
    return offer_id.hex


async def get_story_offer(offer_id: str) -> dict[str, Any] | None:
    db = require_pool()
    row = await db.fetchrow(
        """
        select id, telegram_user_id, narrator, options, created_at, expires_at, consumed_at
        from story_offers
        where id = $1
        """,
        UUID(offer_id),
    )
    return dict(row) if row else None


async def reserve_story_offer(offer_id: str) -> bool:
    db = require_pool()
    result = await db.execute(
        """
        update story_offers
        set consumed_at = now()
        where id = $1
          and consumed_at is null
          and expires_at > now()
        """,
        UUID(offer_id),
    )
    return result.endswith("1")


async def release_story_offer(offer_id: str) -> None:
    db = require_pool()
    await db.execute(
        "update story_offers set consumed_at = null where id = $1",
        UUID(offer_id),
    )


async def create_story(
    *,
    title: str,
    full_text: str,
    summary: str,
    narrator: str,
    selected_option: str,
    offered_options: list[dict[str, Any]],
    characters_used: list[str] | None,
    locations_used: list[str] | None,
    new_lore_proposals: list[str] | None,
    delivered_to_user_id: int,
) -> int:
    db = require_pool()
    story_id = await db.fetchval(
        """
        insert into stories (
            title, full_text, summary, status, narrator, selected_option,
            offered_options, characters_used, locations_used, new_lore_proposals,
                delivered_to_user_id
        )
        values ($1, $2, $3, 'pending', $4, $5, $6::jsonb, $7::jsonb, $8::jsonb,
                $9::jsonb, $10)
        returning id
        """,
        title,
        full_text,
        summary,
        narrator,
        selected_option,
        json.dumps(offered_options, ensure_ascii=False),
        json.dumps(characters_used or [], ensure_ascii=False),
        json.dumps(locations_used or [], ensure_ascii=False),
        json.dumps(new_lore_proposals or [], ensure_ascii=False),
        delivered_to_user_id,
    )
    return int(story_id)


async def mark_story_delivered(story_id: int) -> None:
    db = require_pool()
    await db.execute(
        "update stories set delivered_at = now() where id = $1",
        story_id,
    )


async def consume_daily_story(telegram_user_id: int, story_date: date, story_id: int) -> bool:
    db = require_pool()
    result = await db.execute(
        """
        insert into daily_limits (telegram_user_id, date, story_id)
        values ($1, $2, $3)
        on conflict do nothing
        """,
        telegram_user_id,
        story_date,
        story_id,
    )
    return result.endswith("1")


async def update_story_status(story_id: int, status: str) -> bool:
    db = require_pool()
    result = await db.execute(
        "update stories set status = $1 where id = $2",
        status,
        story_id,
    )
    return result.endswith("1")


async def get_story(story_id: int) -> dict[str, Any] | None:
    db = require_pool()
    row = await db.fetchrow("select * from stories where id = $1", story_id)
    return dict(row) if row else None


async def get_latest_stories(limit: int = 5) -> list[dict[str, Any]]:
    db = require_pool()
    rows = await db.fetch(
        """
        select id, title, summary, status, narrator, created_at
        from stories
        order by created_at desc
        limit $1
        """,
        limit,
    )
    return [dict(row) for row in rows]


async def get_recent_story_summaries(narrator: str, limit: int = 5) -> list[str]:
    db = require_pool()
    rows = await db.fetch(
        """
        select title, summary
        from stories
        where narrator = $1
        order by created_at desc
        limit $2
        """,
        narrator,
        limit,
    )
    return [f"{row['title']}: {row['summary']}" for row in rows]


async def get_recent_story_memories(narrator: str, limit: int = 8) -> list[dict[str, Any]]:
    db = require_pool()
    rows = await db.fetch(
        """
        select id, title, summary, selected_option, offered_options, characters_used,
               locations_used, created_at
        from stories
        where narrator = $1
        order by created_at desc
        limit $2
        """,
        narrator,
        limit,
    )
    return [dict(row) for row in rows]


async def get_latest_delivered_story(
    *,
    narrator: str,
    telegram_user_id: int,
) -> dict[str, Any] | None:
    db = require_pool()
    row = await db.fetchrow(
        """
        select id, title, summary, selected_option, offered_options, characters_used,
               locations_used, new_lore_proposals, created_at, delivered_at
        from stories
        where narrator = $1
          and delivered_to_user_id = $2
          and delivered_at is not null
        order by delivered_at desc
        limit 1
        """,
        narrator,
        telegram_user_id,
    )
    return dict(row) if row else None


async def create_auto_reply_draft(
    *,
    animal_key: str,
    incoming_chat_id: int,
    incoming_text: str,
    proposed_text: str,
    reason: str | None = None,
) -> int:
    db = require_pool()
    draft_id = await db.fetchval(
        """
        insert into auto_reply_drafts (
            animal_key, incoming_chat_id, incoming_text, proposed_text, reason
        )
        values ($1, $2, $3, $4, $5)
        returning id
        """,
        animal_key,
        incoming_chat_id,
        incoming_text,
        proposed_text,
        reason,
    )
    return int(draft_id)


async def get_auto_reply_draft(draft_id: int) -> dict[str, Any] | None:
    db = require_pool()
    row = await db.fetchrow(
        "select * from auto_reply_drafts where id = $1",
        draft_id,
    )
    return dict(row) if row else None


async def reserve_auto_reply_draft(draft_id: int, admin_user_id: int) -> dict[str, Any] | None:
    db = require_pool()
    row = await db.fetchrow(
        """
        update auto_reply_drafts
        set status = 'sending',
            reviewed_at = now(),
            admin_user_id = $2
        where id = $1 and status = 'pending'
        returning *
        """,
        draft_id,
        admin_user_id,
    )
    return dict(row) if row else None


async def mark_auto_reply_draft_sent(draft_id: int) -> None:
    db = require_pool()
    await db.execute(
        """
        update auto_reply_drafts
        set status = 'sent',
            sent_at = now()
        where id = $1
        """,
        draft_id,
    )


async def release_auto_reply_draft(draft_id: int) -> None:
    db = require_pool()
    await db.execute(
        "update auto_reply_drafts set status = 'pending' where id = $1 and status = 'sending'",
        draft_id,
    )


async def reject_auto_reply_draft(draft_id: int, admin_user_id: int) -> bool:
    db = require_pool()
    result = await db.execute(
        """
        update auto_reply_drafts
        set status = 'rejected',
            reviewed_at = now(),
            admin_user_id = $2
        where id = $1 and status = 'pending'
        """,
        draft_id,
        admin_user_id,
    )
    return result.endswith("1")


async def get_system_status_counts() -> dict[str, Any]:
    db = require_pool()
    row = await db.fetchrow(
        """
        select
            (select count(*) from stories) as stories_total,
            (select count(*) from stories where status = 'pending') as stories_pending,
            (select count(*) from stories where status = 'canon') as stories_canon,
            (select count(*) from story_offers where consumed_at is null and expires_at > now()) as active_story_offers,
            (select count(*) from auto_reply_drafts where status = 'pending') as auto_reply_pending,
            (select count(*) from auto_reply_drafts where status = 'sent') as auto_reply_sent
        """
    )
    return dict(row) if row else {}
