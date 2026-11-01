from datetime import datetime, timedelta, timezone

# Campo Grande - MS is UTC-4 all year (no daylight saving since 2019). A fixed offset avoids
# depending on the tzdata package inside the container.
STORE_TZ = timezone(timedelta(hours=-4))

WEEKDAYS = ["segunda-feira", "terça-feira", "quarta-feira", "quinta-feira", "sexta-feira", "sábado", "domingo"]

# Weekday (0 = Monday) -> (opening hour, closing hour). Sunday is closed.
HOURS = {**{d: (9, 18) for d in range(5)}, 5: (9, 13)}


def store_status(now: datetime | None = None) -> dict:
    """Current date/time in Campo Grande and whether the store is open, in Portuguese."""
    now = (now or datetime.now(timezone.utc)).astimezone(STORE_TZ)
    hours = HOURS.get(now.weekday())

    if hours and hours[0] <= now.hour < hours[1]:
        status = f"A loja está ABERTA agora e fecha às {hours[1]}h."
    elif hours and now.hour < hours[0]:
        status = f"A loja está FECHADA agora e abre hoje às {hours[0]}h."
    else:
        # Closed for the day: find the next day with opening hours.
        status = "A loja está FECHADA agora."
        for ahead in range(1, 8):
            day = now + timedelta(days=ahead)
            if day.weekday() in HOURS:
                when = "amanhã" if ahead == 1 else WEEKDAYS[day.weekday()]
                status = f"A loja está FECHADA agora e volta {when} às {HOURS[day.weekday()][0]}h."
                break

    return {
        "now": f"{WEEKDAYS[now.weekday()]}, {now:%d/%m/%Y}, {now:%H:%M} (horário de Campo Grande)",
        "status": status,
    }
