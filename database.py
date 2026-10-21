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

            create table if not exists court_cases (
                id bigserial primary key,
                chat_id bigint not null,
                accusation text not null,
                status text not null default 'active',
                verdict text,
                sentence_text text,
                created_at timestamptz not null default now(),
                sentenced_at timestamptz,
                closed_at timestamptz
            );

            create table if not exists court_messages (
                id bigserial primary key,
                case_id bigint not null references court_cases(id),
                sender text not null,
                text text not null,
                created_at timestamptz not null default now()
            );

            create table if not exists conversation_messages (
                id bigserial primary key,
                chat_id bigint not null,
                animal_key text not null check (animal_key in ('castori', 'mimosuga', 'vaca', 'corte', 'dulcimiel')),
                source_key text not null,
                event_id bigint,
                source text not null,
                role text not null check (role in ('user', 'assistant')),
                message_text text not null,
                occurred_at timestamptz,
                message_id bigint,
                epoch bigint not null default 0,
                recorded_at timestamptz not null default now(),
                unique (chat_id, animal_key, source_key)
            );
            create index if not exists conversation_messages_page_idx
                on conversation_messages (chat_id, animal_key, epoch, occurred_at desc, source_key desc);
            create index if not exists stories_delivered_library_idx
                on stories (delivered_to_user_id, delivered_at desc, id desc)
                where delivered_at is not null;
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


async def get_pending_auto_reply_drafts(*, animal_key: str, chat_id: int,
                                       limit: int = 20) -> list[dict[str, Any]]:
    """Pending proposals for the currently linked recipient, for private Centralita."""
    db = require_pool()
    rows = await db.fetch(
        """
        select id, animal_key, incoming_chat_id, incoming_text, proposed_text, status, created_at
        from auto_reply_drafts
        where status = 'pending' and animal_key = $1 and incoming_chat_id = $2
        order by created_at desc, id desc
        limit $3
        """,
        animal_key, chat_id, max(1, min(int(limit), 100)),
    )
    return [dict(row) for row in rows]


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
            (select count(*) from auto_reply_drafts where status = 'sent') as auto_reply_sent,
            (select count(*) from court_cases where status = 'active') as court_cases_active
        """
    )
    return dict(row) if row else {}


async def create_court_case(*, chat_id: int, accusation: str, accuser: str = "admin") -> int:
    db = require_pool()
    async with db.acquire() as conn:
        async with conn.transaction():
            existing = await conn.fetchval(
                """
                select id from court_cases
                where chat_id = $1 and status = 'active'
                order by created_at desc
                limit 1
                """,
                chat_id,
            )
            if existing:
                raise RuntimeError(f"Ya existe una causa activa: {existing}")
            case_id = await conn.fetchval(
                """
                insert into court_cases (chat_id, accusation)
                values ($1, $2)
                returning id
                """,
                chat_id,
                accusation,
            )
            await conn.execute(
                """
                insert into court_messages (case_id, sender, text)
                values ($1, $2, $3)
                """,
                case_id,
                accuser,
                accusation,
            )
    return int(case_id)


async def get_active_court_case(chat_id: int) -> dict[str, Any] | None:
    db = require_pool()
    row = await db.fetchrow(
        """
        select * from court_cases
        where chat_id = $1 and status = 'active'
        order by created_at desc
        limit 1
        """,
        chat_id,
    )
    return dict(row) if row else None


async def get_latest_court_case(chat_id: int) -> dict[str, Any] | None:
    db = require_pool()
    row = await db.fetchrow(
        """
        select * from court_cases
        where chat_id = $1
        order by created_at desc
        limit 1
        """,
        chat_id,
    )
    return dict(row) if row else None


async def add_court_message(case_id: int, sender: str, text: str) -> None:
    db = require_pool()
    await db.execute(
        """
        insert into court_messages (case_id, sender, text)
        values ($1, $2, $3)
        """,
        case_id,
        sender,
        text,
    )


async def get_court_messages(case_id: int, limit: int = 30) -> list[dict[str, Any]]:
    db = require_pool()
    rows = await db.fetch(
        """
        select sender, text, created_at
        from court_messages
        where case_id = $1
        order by created_at desc
        limit $2
        """,
        case_id,
        limit,
    )
    return [dict(row) for row in reversed(rows)]


async def get_recent_court_precedents(limit: int = 5) -> list[dict[str, Any]]:
    db = require_pool()
    rows = await db.fetch(
        """
        select id, accusation, verdict, sentence_text, sentenced_at
        from court_cases
        where status = 'sentenced'
        order by sentenced_at desc nulls last
        limit $1
        """,
        limit,
    )
    return [dict(row) for row in rows]


async def sentence_court_case(
    *,
    case_id: int,
    verdict: str,
    sentence_text: str,
) -> None:
    db = require_pool()
    await db.execute(
        """
        update court_cases
        set status = 'sentenced',
            verdict = $2,
            sentence_text = $3,
            sentenced_at = now()
        where id = $1 and status = 'active'
        """,
        case_id,
        verdict,
        sentence_text,
    )


async def archive_conversation_event(*, chat_id: int, animal_key: str, source_key: str,
                                     event_id: int | None, source: str, role: str, text: str,
                                     occurred_at: datetime | None, epoch: int = 0,
                                     message_id: int | None = None) -> None:
    """Idempotent journal of delivered/incoming events; never stores consultations."""
    if animal_key == "salchicher":
        raise ValueError("Private consultations must not enter the durable archive")
    await require_pool().execute(
        """
        insert into conversation_messages
            (chat_id, animal_key, source_key, event_id, source, role, message_text,
             occurred_at, epoch, message_id)
        values ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
        on conflict (chat_id, animal_key, source_key) do nothing
        """,
        chat_id, animal_key, source_key, event_id, source, role, text,
        occurred_at, epoch, message_id,
    )


async def get_conversation_archive(*, chat_id: int, animal_key: str, epoch: int = 0,
                                    before_time: datetime | None = None,
                                    before_key: str | None = None, limit: int = 80) -> list[dict[str, Any]]:
    if animal_key == "salchicher":
        return []
    rows = await require_pool().fetch(
        """
        select id, event_id, source_key, source, role, message_text as text,
               occurred_at, message_id, epoch
        from conversation_messages
        where chat_id = $1 and animal_key = $2 and epoch = $3
          and ($5::text is null
               or ($4::timestamptz is null and occurred_at is null and source_key < $5)
               or ($4::timestamptz is not null and
                   (occurred_at < $4 or (occurred_at = $4 and source_key < $5) or occurred_at is null)))
        order by occurred_at desc nulls last, source_key desc
        limit $6
        """,
        chat_id, animal_key, epoch, before_time, before_key, limit,
    )
    return [dict(row) for row in rows]


async def delete_conversation_archive_before_epoch(*, chat_id: int, animal_key: str, epoch: int) -> None:
    await require_pool().execute(
        "delete from conversation_messages where chat_id = $1 and animal_key = $2 and epoch < $3",
        chat_id, animal_key, epoch,
    )


async def get_delivered_stories(*, chat_id: int, before_time: datetime | None = None,
                                before_id: int | None = None, limit: int = 13) -> list[dict[str, Any]]:
    """Editorial status is independent from delivery; pending delivered stories belong here."""
    rows = await require_pool().fetch(
        """
        select id, title, summary, narrator, created_at, delivered_at
        from stories
        where delivered_to_user_id = $1 and delivered_at is not null
          and ($2::timestamptz is null or (delivered_at, id) < ($2, $3::bigint))
        order by delivered_at desc, id desc
        limit $4
        """,
        chat_id, before_time, before_id, limit,
    )
    return [dict(row) for row in rows]


async def get_delivered_story(*, chat_id: int, story_id: int) -> dict[str, Any] | None:
    row = await require_pool().fetchrow(
        """
        select id, title, full_text, summary, narrator, created_at, delivered_at
        from stories
        where id = $1 and delivered_to_user_id = $2 and delivered_at is not null
        """,
        story_id, chat_id,
    )
    return dict(row) if row else None


async def get_sent_auto_reply_archive(*, chat_id: int, cutover: datetime,
                                      before_time: datetime | None = None,
                                      before_key: str | None = None, limit: int = 80,
                                      known_messages: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    """Recover confirmed Mimosuga drafts, retaining grouped input as the stored block.

    Input has no original received timestamp: occurred_at stays NULL, while sort_at
    and recorded_at use the actual draft creation time without claiming receipt time.
    """
    rows = await require_pool().fetch(
        """
        with overlap_sources as (
            select coalesce('event:' || event_id::text, 'archive:' || id::text) as identity,
                   message_text as text, date_trunc('second', occurred_at) as second
            from conversation_messages
            where chat_id = $1 and animal_key = 'mimosuga' and epoch = 0
              and role = 'assistant' and occurred_at is not null
            union
            select item->>'identity', item->>'text', date_trunc('second', (item->>'time')::timestamptz)
            from jsonb_array_elements($6::jsonb) as item
            where item->>'role' = 'assistant' and item->>'time' is not null
        ), overlap_counts as (
            select text, second, count(*) as occurrences from overlap_sources group by text, second
        ), delivered as (
            select id, incoming_text, proposed_text, created_at, sent_at,
                   row_number() over (partition by proposed_text, date_trunc('second', sent_at)
                                      order by id) as overlap_rank
            from auto_reply_drafts
            where incoming_chat_id = $1 and animal_key = 'mimosuga'
              and status = 'sent' and sent_at is not null and created_at < $2 and sent_at < $2
        ), archive as (
            select id, 'draft:' || lpad(id::text, 20, '0') || ':in' as source_key,
                   'user' as role, incoming_text as text, null::timestamptz as occurred_at,
                   created_at as sort_at, created_at as recorded_at, null::bigint as overlap_rank
            from delivered
            union all
            select id, 'draft:' || lpad(id::text, 20, '0') || ':out' as source_key,
                   'assistant' as role, proposed_text as text, sent_at as occurred_at,
                   sent_at as sort_at, created_at as recorded_at, overlap_rank
            from delivered
        )
        select * from archive
        where ($4::text is null or ($3::timestamptz is not null and
              (sort_at < $3 or (sort_at = $3 and source_key < $4))))
          and (role <> 'assistant' or overlap_rank > coalesce(
              (select occurrences from overlap_counts c
               where c.text = archive.text and c.second = date_trunc('second', archive.occurred_at)), 0))
        order by sort_at desc, source_key desc
        limit $5
        """,
        chat_id, cutover, before_time, before_key, limit, json.dumps(known_messages or []),
    )
    return [dict(row) for row in rows]
