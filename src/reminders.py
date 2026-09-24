"""Deadline-Reminder: Einträge, die du verfolgst und deren Deadline bald ansteht."""
from __future__ import annotations

from datetime import date
from typing import Iterable

from .models import ACTIVE_STATUSES, Opportunity


def deadline_reminders(
    entries: Iterable[Opportunity], today: date, days: Iterable[int] = (7, 2)
) -> list[tuple[Opportunity, int]]:
    """Gibt (Eintrag, Tage bis Deadline) zurück für Einträge mit Status 'interessant'
    oder 'in_vorbereitung', deren Deadline GENAU in 7 oder 2 Tagen ist (Werte aus settings.yaml).

    Der Lauf ist täglich, deshalb kommt jeder Reminder genau einmal pro Stufe.
    """
    stufen = set(days)
    result = []
    for o in entries:
        if o.status in ACTIVE_STATUSES and o.deadline is not None:
            rest = (o.deadline - today).days
            if rest in stufen:
                result.append((o, rest))
    result.sort(key=lambda item: item[1])
    return result
