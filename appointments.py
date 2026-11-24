"""In-memory demo data. The functions in this file never call an AI service."""

import re
from datetime import datetime, timedelta
from threading import Lock
from zoneinfo import ZoneInfo


class Appointments:
    def __init__(self):
        self.lock = Lock()
        self.doctors = [
            {"id": "rao", "name": "Dr. Anika Rao", "specialty": "General medicine", "initials": "AR"},
            {"id": "sen", "name": "Dr. Rohan Sen", "specialty": "Dermatology", "initials": "RS"},
            {"id": "mehta", "name": "Dr. Mira Mehta", "specialty": "Pediatrics", "initials": "MM"},
        ]
        tomorrow = datetime.now(ZoneInfo("Asia/Kolkata")).date() + timedelta(days=1)
        self.slots = {
            f"{doctor['id']}-{day}-{hour}": {
                "slot_id": f"{doctor['id']}-{day}-{hour}",
                "doctor_id": doctor["id"], "doctor": doctor["name"],
                "date": (tomorrow + timedelta(days=day)).isoformat(),
                "time": f"{hour:02}:00",
            }
            for doctor in self.doctors
            for day in range(2)
            for hour in (10, 11, 15)
        }
        self.bookings = {}
        self.next_number = 1

    def available(self, doctor="", date=""):
        if not isinstance(doctor, str) or not isinstance(date, str):
            return {"ok": False, "reason": "Use a doctor name and a date as text."}
        doctor = doctor.strip().lower()
        date = date.strip()
        with self.lock:
            taken = {item["slot_id"] for item in self.bookings.values()}
            slots = [
                slot for slot in self.slots.values()
                if slot["slot_id"] not in taken
                and (not doctor or doctor in slot["doctor"].lower())
                and (not date or date == slot["date"])
            ]
        return {"ok": True, "timezone": "Asia/Kolkata", "slots": slots}

    def book(self, slot_id, phone, confirmed):
        phone = normalize_phone(phone)
        if confirmed is not True or phone is None:
            return {"ok": False, "reason": "Read back a valid phone number and get confirmation first."}
        with self.lock:
            slot = self.slots.get(slot_id) if isinstance(slot_id, str) else None
            if slot is None:
                return {"ok": False, "reason": "Unknown slot. Check availability again."}
            existing = self.bookings.get(phone)
            if existing:
                if existing["slot_id"] == slot_id:
                    return {"ok": True, "appointment": existing, "already_booked": True}
                return {"ok": False, "reason": "This caller already has an active appointment."}
            if any(item["slot_id"] == slot_id for item in self.bookings.values()):
                return {"ok": False, "reason": "The slot is taken. Check availability again."}
            appointment = {**slot, "reference": f"AP-{self.next_number:03}", "phone_end": phone[-4:]}
            self.next_number += 1
            self.bookings[phone] = appointment
            return {"ok": True, "appointment": appointment}

    def cancel(self, phone, confirmed):
        phone = normalize_phone(phone)
        if confirmed is not True or phone is None:
            return {"ok": False, "reason": "Read back a valid phone number and get confirmation first."}
        with self.lock:
            appointment = self.bookings.pop(phone, None)
        if appointment is None:
            return {"ok": False, "reason": "There is no active appointment for that number."}
        return {"ok": True, "appointment": appointment}

    def snapshot(self):
        with self.lock:
            return {"doctors": self.doctors, "slots": list(self.slots.values()),
                    "appointments": list(self.bookings.values())}


def normalize_phone(phone):
    """Accept a spoken international number or assume India for ten local digits."""
    if not isinstance(phone, str) or not re.fullmatch(r"\+?[0-9 ()-]+", phone.strip()):
        return None
    text = phone.strip()
    digits = re.sub(r"[^0-9]", "", text)
    if text.startswith("+") and 8 <= len(digits) <= 15 and not digits.startswith("0"):
        return f"+{digits}"
    if not text.startswith("+") and len(digits) == 10:
        return f"+91{digits}"
    return None
