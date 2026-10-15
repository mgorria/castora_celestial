"""Private December visit plans; only approved event text reaches Sandra."""

import asyncio
import uuid
from datetime import datetime, timedelta
from typing import Any, Callable
from zoneinfo import ZoneInfo


EVENTS = ("pista1", "pista2", "manana")
FINAL_EVENTS = {"sent", "uncertain", "sending"}
MAX_LATENESS = timedelta(hours=2)
SEND_TIMEOUT_SECONDS = 30


async def generate_visit_messages(gifts: str) -> dict:
    from vaca_service import generate_visit_messages as generate
    return await generate(gifts)


class VacaCampaigns:
    def __init__(self, load: Callable, save: Callable, recipient: Callable,
                 send: Callable, notify: Callable, timezone,
                 paused: Callable = lambda: False):
        self.load, self.save = load, save
        self.recipient, self.send, self.notify = recipient, send, notify
        self.timezone = ZoneInfo(timezone) if isinstance(timezone, str) else timezone
        self.paused = paused
        self._inflight: set[str] = set()

    def now(self) -> datetime:
        return datetime.now(self.timezone)

    def state(self) -> dict:
        return self.load().get("vaca_campaigns", {"paused": False, "plans": {}})

    def store(self, state: dict) -> None:
        data = self.load()
        data["vaca_campaigns"] = state
        self.save(data)

    def parse_date(self, date_text: str, time_text: str) -> datetime:
        try:
            value = datetime.strptime(f"{date_text} {time_text}", "%d/%m/%Y %H:%M")
        except ValueError as exc:
            raise ValueError("Fecha no válida. Usa DD/MM/AAAA HH:MM.") from exc
        value = value.replace(tzinfo=self.timezone)
        if value.month != 12:
            raise ValueError("Las visitas y pistas deben estar en diciembre.")
        if value <= self.now():
            raise ValueError("La fecha debe estar en el futuro.")
        return value

    def event_times(self, delivery: datetime) -> dict[str, datetime]:
        return {
            "pista1": (delivery - timedelta(days=3)).replace(hour=18, minute=0),
            "pista2": (delivery - timedelta(days=1)).replace(hour=18, minute=0),
            "manana": delivery,
        }

    def prepare_events(self, delivery: datetime, texts: dict[str, str],
                       old: dict | None = None) -> dict:
        now = self.now()
        result = {}
        for name, when in self.event_times(delivery).items():
            previous = (old or {}).get(name, {})
            if previous.get("status") in FINAL_EVENTS:
                result[name] = previous
                continue
            result[name] = {
                "at": when.isoformat(), "text": texts[name],
                "status": "pending" if when.month == 12 and when > now else "skipped",
            }
        return result

    def get_plan(self, state: dict, plan_id: str, editable: bool = False) -> dict:
        plan = state.get("plans", {}).get(plan_id)
        if not plan:
            raise ValueError("No encuentro esa visita. Usa /vaca_visitas.")
        if editable and plan["status"] in {"cancelled", "completed"}:
            raise ValueError("Esa visita ya está cerrada. Crea otra para una nueva entrega.")
        return plan

    def make_draft(self, plan: dict) -> None:
        plan["status"] = "draft"
        plan["revision"] = plan.get("revision", 0) + 1

    def display_time(self, value: str) -> str:
        return datetime.fromisoformat(value).astimezone(self.timezone).strftime("%d/%m/%Y %H:%M")

    def preview(self, plan: dict) -> str:
        status = {"draft": "borrador", "active": "activa", "cancelled": "cancelada",
                  "completed": "finalizada"}.get(plan["status"], plan["status"])
        lines = [f"Visita {plan['id']} · {status}",
                 f"Entrega prevista: {self.display_time(plan['delivery_at'])} ({self.timezone})",
                 f"Regalos (privado): {plan['gifts']}",
                 "El mensaje de la mañana presupone que colocarás los regalos para esa fecha; "
                 "el bot no verifica la entrega física."]
        for name in EVENTS:
            event = plan["events"][name]
            lines.append(f"\n{name} · {self.display_time(event['at'])} · {event['status']}\n{event['text']}")
        if plan["status"] == "draft":
            lines.append(f"\nPara activar este borrador: /vaca_activar {plan['id']}")
        return "\n".join(lines)

    async def reply(self, update, text: str) -> None:
        # Telegram's text ceiling applies even to private previews.
        for start in range(0, len(text), 3500):
            await update.effective_chat.send_message(text[start:start + 3500])

    async def safe_notify(self, text: str) -> None:
        try:
            await self.notify(text)
        except Exception:
            # Delivery state is already persisted; notification failure must not replay it.
            pass

    async def handle_admin(self, update, context) -> None:
        # The caller verifies the owner's ID; also refuse accidental group disclosure.
        if not update.effective_chat or update.effective_chat.type != "private" or not update.message:
            return
        raw = (update.message.text or "").strip()
        command, _, body = raw.partition(" ")
        command = command.split("@", 1)[0].lower()
        try:
            if command == "/vaca_visita":
                await self.create(update, body)
                return
            if command == "/vaca_visitas":
                state = self.state()
                if body.strip():
                    await self.reply(update, self.preview(self.get_plan(state, body.strip())))
                else:
                    plans = state.get("plans", {})
                    lines = [f"Visitas de la Vaca · pausa: {'sí' if state.get('paused') else 'no'}"]
                    lines.extend(f"{p['id']} · {p['status']} · {self.display_time(p['delivery_at'])}"
                                 for p in plans.values())
                    if not plans:
                        lines.append("No hay visitas. /vaca_visita DD/MM/AAAA HH:MM | regalos")
                    await self.reply(update, "\n".join(lines))
                return
            if command == "/vaca_pausa":
                if body.strip().lower() not in {"on", "off"}:
                    raise ValueError("Uso: /vaca_pausa on|off")
                state = self.state()
                state["paused"] = body.strip().lower() == "on"
                self.store(state)
                await self.reply(update, "Visitas pausadas." if state["paused"] else
                                 "Visitas reanudadas; los mensajes vencidos hace más de 2 horas caducan.")
                return
            if command not in {"/vaca_activar", "/vaca_texto", "/vaca_hora", "/vaca_fecha", "/vaca_cancelar"}:
                await self.reply(update, "Comandos: /vaca_visita, /vaca_visitas, /vaca_activar, "
                                 "/vaca_texto, /vaca_hora, /vaca_fecha, /vaca_cancelar, /vaca_pausa.")
                return
            parts = body.split()
            if not parts:
                raise ValueError(f"Indica el ID de visita: {command} ID")
            state = self.state()
            plan = self.get_plan(state, parts[0], editable=command != "/vaca_cancelar")
            if command == "/vaca_activar":
                recipient = self.recipient()
                if not recipient:
                    raise ValueError("Sandra debe iniciar primero el bot con /start para vincularlo.")
                if plan["status"] == "active":
                    raise ValueError("Esta visita ya está activa.")
                if datetime.fromisoformat(plan["delivery_at"]) <= self.now():
                    raise ValueError("La entrega prevista ya ha pasado. Reprograma con /vaca_fecha.")
                for event in plan["events"].values():
                    if event["status"] == "pending" and datetime.fromisoformat(event["at"]) <= self.now():
                        event["status"] = "expired"
                if not any(e["status"] == "pending" for e in plan["events"].values()):
                    raise ValueError("La visita no tiene mensajes futuros pendientes.")
                plan["recipient_id"] = int(recipient)
                plan["status"] = "active"
            elif command == "/vaca_cancelar":
                plan["status"] = "cancelled"
                for event in plan["events"].values():
                    if event["status"] in {"pending", "skipped"}:
                        event["status"] = "cancelled"
            elif command == "/vaca_texto":
                left, separator, text = body.partition("|")
                fields = left.split()
                if len(fields) != 2 or not separator or not text.strip():
                    raise ValueError("Uso: /vaca_texto ID pista1|pista2|manana | texto")
                event = self.editable_event(plan, fields[1])
                if len(text.strip()) > 3500:
                    raise ValueError("El texto puede tener como máximo 3500 caracteres.")
                event["text"] = text.strip()
                self.make_draft(plan)
            elif command == "/vaca_hora":
                if len(parts) != 4:
                    raise ValueError("Uso: /vaca_hora ID EVENTO DD/MM/AAAA HH:MM")
                event = self.editable_event(plan, parts[1])
                when = self.parse_date(parts[2], parts[3])
                delivery = datetime.fromisoformat(plan["delivery_at"])
                if parts[1] != "manana" and (when >= delivery or when.year != delivery.year):
                    raise ValueError("La pista debe ser anterior a la entrega y en el mismo diciembre.")
                if parts[1] == "manana":
                    if when.year != delivery.year:
                        raise ValueError("Para cambiar el año de la entrega usa /vaca_fecha; así se reorganizan también las pistas pendientes.")
                    if any(e["status"] == "pending" and datetime.fromisoformat(e["at"]) >= when
                           for key, e in plan["events"].items() if key != "manana"):
                        raise ValueError("Hay pistas posteriores a esa hora. Usa /vaca_fecha para reorganizar la visita.")
                    plan["delivery_at"] = when.isoformat()
                event.update(at=when.isoformat(), status="pending")
                self.make_draft(plan)
            elif command == "/vaca_fecha":
                if len(parts) != 3:
                    raise ValueError("Uso: /vaca_fecha ID DD/MM/AAAA HH:MM")
                if plan["events"]["manana"]["status"] in FINAL_EVENTS:
                    raise ValueError("El mensaje de la mañana ya se envió o su envío es incierto. Crea otra visita.")
                delivery = self.parse_date(parts[1], parts[2])
                texts = {name: plan["events"][name]["text"] for name in EVENTS}
                plan["events"] = self.prepare_events(delivery, texts, plan["events"])
                plan["delivery_at"] = delivery.isoformat()
                self.make_draft(plan)
            self.store(state)
            await self.reply(update, self.preview(plan))
        except ValueError as exc:
            await self.reply(update, str(exc))

    def editable_event(self, plan: dict, name: str) -> dict:
        if name not in EVENTS:
            raise ValueError("Evento desconocido. Usa pista1, pista2 o manana.")
        event = plan["events"][name]
        if event["status"] in FINAL_EVENTS:
            raise ValueError("Ese mensaje ya se envió, está enviándose o tiene envío incierto; no se reenviará.")
        return event

    async def create(self, update, body: str) -> None:
        left, separator, gifts = body.partition("|")
        parts = left.split()
        if len(parts) != 2 or not separator or not gifts.strip():
            raise ValueError("Uso: /vaca_visita DD/MM/AAAA HH:MM | regalos")
        delivery = self.parse_date(*parts)
        gifts = gifts.strip()
        if len(gifts) > 2000:
            raise ValueError("Resume los regalos en un máximo de 2000 caracteres.")
        try:
            generated = await generate_visit_messages(gifts)
            clues = generated.get("clues")
            morning = generated.get("morning")
            if not isinstance(clues, list) or len(clues) != 2:
                raise ValueError("invalid clues")
            texts = dict(zip(EVENTS, [*clues, morning]))
            if any(not isinstance(t, str) or not t.strip() or len(t) > 3500 for t in texts.values()):
                raise ValueError("invalid texts")
        except Exception:
            await self.reply(update, "No he podido preparar los tres mensajes. No se ha creado ninguna visita; vuelve a intentarlo.")
            return
        # Generation may take time; validate again and reload before persisting.
        if delivery <= self.now():
            raise ValueError("La fecha ha pasado mientras preparaba los mensajes. Elige otra fecha.")
        state = self.state()
        plans = state.setdefault("plans", {})
        plan_id = uuid.uuid4().hex[:8]
        while plan_id in plans:
            plan_id = uuid.uuid4().hex[:8]
        plan = {"id": plan_id, "status": "draft", "revision": 1, "gifts": gifts,
                "delivery_at": delivery.isoformat(), "created_at": self.now().isoformat(),
                "events": self.prepare_events(delivery, texts)}
        plans[plan_id] = plan
        self.store(state)
        await self.reply(update, self.preview(plan))

    async def tick(self, now: datetime | None = None) -> None:
        now = now or self.now()
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("tick requires a timezone-aware datetime")
        # Snapshot only IDs. Every mutation reloads current state after each await.
        for plan_id in list(self.state().get("plans", {})):
            for name in EVENTS:
                state = self.state()
                plan = state.get("plans", {}).get(plan_id)
                if not plan:
                    break
                event = plan["events"][name]
                attempt = event.get("attempt")
                if event["status"] == "sending" and attempt not in self._inflight:
                    event["status"] = "uncertain"
                    self.store(state)
                    await self.safe_notify(f"Visita {plan_id}, {name}: envío interrumpido; no se reintentará automáticamente.")
                    continue
                if state.get("paused") or self.paused() or plan["status"] != "active":
                    continue
                if event["status"] != "pending":
                    continue
                if self.recipient() != plan.get("recipient_id"):
                    self.make_draft(plan)
                    self.store(state)
                    await self.safe_notify(f"Visita {plan_id}: cambió o falta el destinatario vinculado. Vuelve a revisar y activar el borrador.")
                    break
                when = datetime.fromisoformat(event["at"])
                if now < when:
                    continue
                if now - when > MAX_LATENESS:
                    event["status"] = "expired"
                    self.store(state)
                    await self.safe_notify(f"Visita {plan_id}, {name}: mensaje caducado por más de 2 horas de retraso; no se enviará.")
                    continue
                attempt = uuid.uuid4().hex
                event.update(status="sending", attempt=attempt, reserved_at=now.isoformat())
                self.store(state)
                self._inflight.add(attempt)
                try:
                    await asyncio.wait_for(self.send(plan["recipient_id"], event["text"]),
                                           timeout=SEND_TIMEOUT_SECONDS)
                    result = "sent"
                except asyncio.CancelledError:
                    # Persisted reservation is deliberately left ambiguous for restart recovery.
                    raise
                except Exception:
                    result = "uncertain"
                finally:
                    self._inflight.discard(attempt)
                state = self.state()
                current = state.get("plans", {}).get(plan_id)
                current_event = current and current["events"].get(name)
                if current_event and current_event.get("attempt") == attempt and current_event["status"] == "sending":
                    current_event["status"] = result
                    if result == "sent":
                        current_event["sent_at"] = now.isoformat()
                    self.store(state)
                if result == "uncertain":
                    await self.safe_notify(f"Visita {plan_id}, {name}: envío incierto. No se reintentará para evitar duplicados; comprueba el chat.")
            state = self.state()
            plan = state.get("plans", {}).get(plan_id)
            if plan and plan["status"] == "active" and not any(
                    e["status"] in {"pending", "sending"} for e in plan["events"].values()):
                plan["status"] = "completed"
                self.store(state)
