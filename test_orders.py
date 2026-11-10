import os
import sqlite3
import tempfile
import unittest

fd, path = tempfile.mkstemp(suffix=".db")
os.close(fd)
os.environ["DRONEDASH_DB"] = path

import app as desk


def wipe():
    with desk.app.app_context():
        db = desk.get_db()
        db.execute("delete from orders")
        db.execute("delete from users where role != 'operator'")


class OrderTests(unittest.TestCase):
    def setUp(self):
        wipe()
        self.client = desk.app.test_client()

    def register(self, email="ada@kent.edu"):
        return self.client.post(
            "/register",
            data={
                "name": "Ada",
                "email": email,
                "phone": "330-555-0199",
                "password": "secret",
            },
            follow_redirects=True,
        )

    def test_missing_field_is_refused(self):
        rv = self.client.post(
            "/register",
            data={"name": "Ada", "email": "ada@kent.edu", "phone": "", "password": "x"},
        )
        self.assertIn(b"Fill out every field", rv.data)

    def test_bad_window_is_not_saved(self):
        self.register()
        rv = self.client.post(
            "/orders",
            data={
                "pickup": "Public Square",
                "dest": "Ohio City",
                "package": "book",
                "start": "2026-11-10T15:00",
                "end": "2026-11-10T14:00",
            },
        )
        self.assertIn(b"Window end has to be after the start", rv.data)
        self.assertIn(b"No orders yet", rv.data)
        db = sqlite3.connect(path)
        count = db.execute("select count(*) from orders").fetchone()[0]
        db.close()
        self.assertEqual(count, 0)

    def test_order_is_saved_and_still_there_later(self):
        self.register()
        rv = self.client.post(
            "/orders",
            data={
                "pickup": "Public Square",
                "dest": "Ohio City",
                "package": "book",
                "start": "2026-11-10T15:00",
                "end": "2026-11-10T16:00",
            },
        )
        self.assertIn(b"Pending", rv.data)
        db = sqlite3.connect(path)
        row = db.execute(
            "select pickup, status from orders"
        ).fetchone()
        db.close()
        self.assertEqual(row, ("Public Square", "Pending"))

        again = desk.app.test_client()
        again.post(
            "/login",
            data={"email": "ada@kent.edu", "password": "secret"},
            follow_redirects=True,
        )
        page = again.get("/")
        self.assertIn(b"Public Square", page.data)
        self.assertIn(b"Pending", page.data)

    def test_customer_does_not_see_someone_elses_order(self):
        self.register()
        self.client.post(
            "/orders",
            data={
                "pickup": "Public Square",
                "dest": "Ohio City",
                "package": "book",
                "start": "2026-11-10T15:00",
                "end": "2026-11-10T16:00",
            },
        )
        other = desk.app.test_client()
        other.post(
            "/register",
            data={
                "name": "Bea",
                "email": "bea@kent.edu",
                "phone": "330-555-0188",
                "password": "secret",
            },
            follow_redirects=True,
        )
        page = other.get("/")
        self.assertNotIn(b"Public Square", page.data)

    def test_pending_order_can_be_updated(self):
        self.register()
        self.client.post(
            "/orders",
            data={
                "pickup": "Public Square",
                "dest": "Ohio City",
                "package": "book",
                "start": "2026-11-10T15:00",
                "end": "2026-11-10T16:00",
            },
        )
        db = sqlite3.connect(path)
        oid = db.execute("select id from orders").fetchone()[0]
        db.close()
        rv = self.client.post(
            "/orders/%s/update" % oid,
            data={
                "pickup": "Playhouse Square",
                "dest": "Ohio City",
                "package": "book",
                "start": "2026-11-10T15:00",
                "end": "2026-11-10T16:00",
            },
        )
        self.assertIn(b"Playhouse Square", rv.data)

    def test_operator_can_filter(self):
        self.register()
        self.client.post(
            "/orders",
            data={
                "pickup": "Public Square",
                "dest": "Ohio City",
                "package": "book",
                "start": "2026-11-10T15:00",
                "end": "2026-11-10T16:00",
            },
        )
        op = desk.app.test_client()
        op.post(
            "/login",
            data={"email": "operator@kent.edu", "password": "password"},
            follow_redirects=True,
        )
        found = op.get("/?q=Ada")
        self.assertIn(b"Public Square", found.data)
        missing = op.get("/?q=zzzz-nope")
        self.assertIn(b"No orders match", missing.data)


if __name__ == "__main__":
    unittest.main()
