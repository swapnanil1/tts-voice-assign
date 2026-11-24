import unittest
from concurrent.futures import ThreadPoolExecutor

from appointments import Appointments


class AppointmentsTest(unittest.TestCase):
    def setUp(self):
        self.store = Appointments()
        self.slot = self.store.available("rao")["slots"][0]["slot_id"]

    def test_confirm_book_retry_and_cancel(self):
        self.assertFalse(self.store.book(self.slot, "+12025550147", False)["ok"])
        booked = self.store.book(self.slot, "+12025550147", True)
        self.assertTrue(booked["ok"])
        self.assertNotIn(self.slot, [s["slot_id"] for s in self.store.available("rao")["slots"]])
        retry = self.store.book(self.slot, "+1 (202) 555-0147", True)
        self.assertEqual(booked["appointment"], retry["appointment"])
        self.assertNotIn("2025550147", str(self.store.snapshot()))
        self.assertFalse(self.store.cancel("+12025550147", False)["ok"])
        self.assertTrue(self.store.cancel("+12025550147", True)["ok"])
        self.assertIn(self.slot, [s["slot_id"] for s in self.store.available("rao")["slots"]])

    def test_competing_bookings_only_one_wins(self):
        with ThreadPoolExecutor(max_workers=2) as executor:
            outcomes = list(executor.map(
                lambda phone: self.store.book(self.slot, phone, True),
                ("+12025550147", "+12025550148"),
            ))
        self.assertEqual(sum(outcome["ok"] for outcome in outcomes), 1)
