## @file app.py
#  @brief DroneDash CLE order desk.
#
#  A customer signs up and places a delivery order.
#  The operator can look through the orders.
#  Records are kept in a sqlite file beside this program.
#
#  @author Nathan Chappie
#  @author Nathan Keim
#  @author Timothy Cherevko
#  @author Ryan Knight
#  @version 0.1

import os
import sqlite3
from datetime import datetime

from flask import Flask, g, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

app = Flask(__name__)
app.secret_key = "dronedash"

## @brief Path of the sqlite file. A test can set DRONEDASH_DB first.
DB = os.environ.get("DRONEDASH_DB") or os.path.join(os.path.dirname(__file__), "dronedash.db")

## @brief Order statuses the desk allows.
STATUSES = ("Pending", "Assigned", "In Transit", "Delivered", "Cancelled")


## @brief Opens the sqlite file for the current request.
#  The same connection is reused until the request ends.
#  @return The open database connection.
def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB, isolation_level=None)
        g.db.row_factory = sqlite3.Row
        g.db.execute("pragma foreign_keys = on")
    return g.db


## @brief Closes the database connection after a request.
#  @param exc The error from the request, if one happened.
@app.teardown_appcontext
def close_db(exc):
    db = g.pop("db", None)
    if db is not None:
        db.close()


## @brief Creates the tables and the operator login if they are missing.
def init_db():
    db = sqlite3.connect(DB, isolation_level=None)
    db.row_factory = sqlite3.Row
    db.execute("pragma foreign_keys = on")
    db.execute(
        """create table if not exists users (
            id integer primary key,
            name text not null,
            email text not null unique,
            phone text not null,
            password_hash text not null,
            role text not null
        )"""
    )
    db.execute(
        """create table if not exists drones (
            id integer primary key,
            name text not null,
            status text not null,
            station text
        )"""
    )
    db.execute(
        """create table if not exists orders (
            id integer primary key,
            customer_id integer not null references users(id),
            pickup text not null,
            dest text not null,
            package text not null,
            window_start text not null,
            window_end text not null,
            status text not null,
            drone_id integer references drones(id),
            departed_at text,
            completed_at text
        )"""
    )
    op = db.execute("select id from users where role = 'operator'").fetchone()
    if op is None:
        db.execute(
            "insert into users (name, email, phone, password_hash, role) values (?,?,?,?,?)",
            (
                "Operator",
                "operator@kent.edu",
                "330-555-0100",
                generate_password_hash("password"),
                "operator",
            ),
        )
    if db.execute("select count(*) c from drones").fetchone()["c"] == 0:
        db.executemany(
            "insert into drones (name, status, station) values (?,?,?)",
            [
                ("Drone 1", "Available", "Public Square"),
                ("Drone 2", "Available", "University Circle"),
                ("Drone 3", "Out of Service", "Ohio City"),
            ],
        )
    db.close()


## @brief Loads the signed-in user before each request.
@app.before_request
def load_user():
    g.user = None
    uid = session.get("uid")
    if not uid:
        return
    g.user = get_db().execute("select * from users where id = ?", (uid,)).fetchone()
    if g.user is None:
        session.clear()


## @brief Tells whether the request came from htmx.
#  @return True when the HX-Request header is set.
def hx():
    return request.headers.get("HX-Request") == "true"


## @brief Sends the user away if they are not signed in, or have the wrong role.
#  @param role Expected role, or None if any signed-in user is allowed.
#  @return A redirect, or None when the user may continue.
def need(role):
    if g.user is None:
        return redirect(url_for("login"))
    if role and g.user["role"] != role:
        return redirect(url_for("home"))
    return None


## @brief Reads the order form and checks the required fields.
#  @return The field values, or None and an error message.
def order_fields():
    pickup = (request.form.get("pickup") or "").strip()
    dest = (request.form.get("dest") or "").strip()
    package = (request.form.get("package") or "").strip()
    start = (request.form.get("start") or "").strip()
    end = (request.form.get("end") or "").strip()
    if not pickup:
        return None, "Pickup location is required."
    if not dest:
        return None, "Dropoff location is required."
    if not package:
        return None, "Package description is required."
    if not start or not end:
        return None, "A delivery window is required."
    try:
        s = datetime.fromisoformat(start)
        e = datetime.fromisoformat(end)
    except ValueError:
        return None, "The delivery window is not a real time."
    if e <= s:
        return None, "Window end has to be after the start."
    return (pickup, dest, package, start, end), None


## @brief Lists one customer's orders, newest first.
#  @param uid The customer id.
#  @return The matching order rows.
def customer_orders(uid):
    return get_db().execute(
        """select o.*, d.name as drone_name
           from orders o
           left join drones d on d.id = o.drone_id
           where o.customer_id = ?
           order by o.id desc""",
        (uid,),
    ).fetchall()


## @brief Copies the order form so a failed submit can be shown again.
#  @return A dict of the posted fields.
def posted_order():
    return {
        "pickup": request.form.get("pickup") or "",
        "dest": request.form.get("dest") or "",
        "package": request.form.get("package") or "",
        "start": request.form.get("start") or "",
        "end": request.form.get("end") or "",
    }


## @brief Draws the customer page, or just the panel when htmx asks.
#  @param error A message to show, or None.
#  @param keep When true, put the posted values back in the form.
#  @return The rendered page.
def render_customer(error=None, keep=False):
    orders = customer_orders(g.user["id"])
    form = posted_order() if keep else {}
    if hx():
        return render_template("customer_panel.html", orders=orders, error=error, form=form)
    return render_template("customer.html", orders=orders, error=error, form=form)


## @brief Draws the operator page, with the current search applied.
#  @param error A message to show, or None.
#  @return The rendered page.
def operator_view(error=None):
    db = get_db()
    q = (request.values.get("q") or "").strip()
    status_filter = request.values.get("status") or ""
    if status_filter not in STATUSES:
        status_filter = ""
    like = "%" + q + "%"
    orders = db.execute(
        """select o.*, u.name as customer_name, d.name as drone_name
           from orders o
           join users u on u.id = o.customer_id
           left join drones d on d.id = o.drone_id
           where (? = '' or o.status = ?)
             and (? = '' or u.name like ? or cast(o.id as text) = ? or o.pickup like ? or o.dest like ?)
           order by o.id desc""",
        (status_filter, status_filter, q, like, q, like, like),
    ).fetchall()
    counts = {s: 0 for s in STATUSES}
    for row in db.execute("select status, count(*) c from orders group by status"):
        if row["status"] in counts:
            counts[row["status"]] = row["c"]
    drones = db.execute("select * from drones order by id").fetchall()
    ctx = dict(
        orders=orders,
        drones=drones,
        counts=counts,
        error=error,
        q=q,
        status_filter=status_filter,
        statuses=STATUSES,
    )
    if hx():
        return render_template("operator_panel.html", **ctx)
    return render_template("operator.html", **ctx)


## @brief Shows the sign-in page, or the desk for whoever is signed in.
@app.get("/")
def home():
    if g.user is None:
        return render_template("login.html", error=None, form={})
    if g.user["role"] == "operator":
        return operator_view()
    return render_customer()


## @brief Signs a customer or the operator in.
@app.route("/login", methods=["GET", "POST"])
def login():
    form = {"email": request.form.get("email", "")}
    error = None
    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""
        form["email"] = email
        user = get_db().execute("select * from users where email = ?", (email,)).fetchone()
        if user is None or not check_password_hash(user["password_hash"], password):
            error = "Wrong email or password."
        else:
            session["uid"] = user["id"]
            return redirect(url_for("home"))
    return render_template("login.html", error=error, form=form)


## @brief Creates a customer account and signs that customer in.
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "GET":
        return render_template("register.html", error=None, form={})
    name = (request.form.get("name") or "").strip()
    email = (request.form.get("email") or "").strip().lower()
    phone = (request.form.get("phone") or "").strip()
    password = request.form.get("password") or ""
    form = {"name": name, "email": email, "phone": phone}
    if not name or not email or not phone or not password:
        return render_template("register.html", error="Fill out every field.", form=form)
    if "@" not in email or "." not in email.split("@")[-1]:
        return render_template("register.html", error="That email does not look right.", form=form)
    try:
        cur = get_db().execute(
            "insert into users (name, email, phone, password_hash, role) values (?,?,?,?,?)",
            (name, email, phone, generate_password_hash(password), "customer"),
        )
    except sqlite3.IntegrityError:
        return render_template("register.html", error="That email is already registered.", form=form)
    session["uid"] = cur.lastrowid
    return redirect(url_for("home"))


## @brief Signs the current user out.
@app.get("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


## @brief Saves a new pending order for the signed-in customer.
@app.post("/orders")
def create_order():
    blocked = need("customer")
    if blocked:
        return blocked
    fields, error = order_fields()
    if error:
        return render_customer(error, keep=True)
    pickup, dest, package, start, end = fields
    get_db().execute(
        """insert into orders
           (customer_id, pickup, dest, package, window_start, window_end, status)
           values (?,?,?,?,?,?, 'Pending')""",
        (g.user["id"], pickup, dest, package, start, end),
    )
    return render_customer()


## @brief Changes a pending order that belongs to the signed-in customer.
#  @param oid The order id.
@app.post("/orders/<int:oid>/update")
def update_order(oid):
    blocked = need("customer")
    if blocked:
        return blocked
    order = get_db().execute("select * from orders where id = ?", (oid,)).fetchone()
    if order is None or order["customer_id"] != g.user["id"]:
        return render_customer("That order is not yours.")
    if order["status"] != "Pending":
        return render_customer("You can only edit an order before a drone is assigned.")
    fields, error = order_fields()
    if error:
        return render_customer(error, keep=True)
    pickup, dest, package, start, end = fields
    get_db().execute(
        """update orders
           set pickup = ?, dest = ?, package = ?, window_start = ?, window_end = ?
           where id = ?""",
        (pickup, dest, package, start, end, oid),
    )
    return render_customer()


## @brief Cancels an order that is still pending or assigned.
#  @param oid The order id.
@app.post("/orders/<int:oid>/cancel")
def cancel_order(oid):
    blocked = need(None)
    if blocked:
        return blocked
    return finish_status(oid, "Cancelled")


## @brief Moves an order to the status the operator asked for.
#  @param oid The order id.
@app.post("/orders/<int:oid>/status")
def order_status(oid):
    blocked = need("operator")
    if blocked:
        return blocked
    return finish_status(oid, request.form.get("next") or "")


## @brief Applies a status change, or refuses it and leaves the saved rows alone.
#  An order that is in transit cannot be cancelled.
#  Marking an order delivered frees its drone.
#  @param oid The order id.
#  @param target The status that was requested.
#  @return The page to show, with an error when the change is refused.
def finish_status(oid, target):
    db = get_db()
    db.execute("BEGIN IMMEDIATE")
    order = db.execute("select * from orders where id = ?", (oid,)).fetchone()
    if order is None:
        db.execute("ROLLBACK")
        return back("Order not found.")
    if g.user["role"] == "customer" and order["customer_id"] != g.user["id"]:
        db.execute("ROLLBACK")
        return back("That order is not yours.")
    current = order["status"]
    now = datetime.now().isoformat(timespec="minutes")

    if target == "Cancelled":
        if current not in ("Pending", "Assigned"):
            db.execute("ROLLBACK")
            return back("You can only cancel an order before it is in transit.")
        db.execute("update orders set status = 'Cancelled' where id = ?", (oid,))
        if current == "Assigned" and order["drone_id"]:
            db.execute(
                "update drones set status = 'Available' where id = ?",
                (order["drone_id"],),
            )
        db.execute("COMMIT")
        return back(None)

    if g.user["role"] != "operator":
        db.execute("ROLLBACK")
        return back("Only the operator can move an order along.")

    if target == "In Transit":
        if current != "Assigned":
            db.execute("ROLLBACK")
            return back("The order has to be assigned before it can go in transit.")
        db.execute(
            "update orders set status = 'In Transit', departed_at = ? where id = ?",
            (now, oid),
        )
        db.execute("COMMIT")
        return back(None)

    if target == "Delivered":
        if current != "In Transit":
            db.execute("ROLLBACK")
            return back("The order has to be in transit before it can be delivered.")
        db.execute(
            "update orders set status = 'Delivered', completed_at = ? where id = ?",
            (now, oid),
        )
        if order["drone_id"]:
            db.execute(
                "update drones set status = 'Available' where id = ?",
                (order["drone_id"],),
            )
        db.execute("COMMIT")
        return back(None)

    db.execute("ROLLBACK")
    return back("That status change is not allowed.")


## @brief Sends the operator or the customer back to their own page.
#  @param error A message to show, or None.
#  @return The rendered page.
def back(error):
    if g.user["role"] == "operator":
        return operator_view(error)
    return render_customer(error)


## @brief Assigns an available drone to a pending order.
#  A drone that is out of service, or already on a delivery, is refused.
#  @param oid The order id.
@app.post("/orders/<int:oid>/assign")
def assign(oid):
    blocked = need("operator")
    if blocked:
        return blocked
    raw = request.form.get("drone_id") or ""
    if not raw.isdigit():
        return operator_view("Pick a drone.")
    drone_id = int(raw)
    db = get_db()
    db.execute("BEGIN IMMEDIATE")
    order = db.execute("select * from orders where id = ?", (oid,)).fetchone()
    drone = db.execute("select * from drones where id = ?", (drone_id,)).fetchone()
    if order is None or drone is None:
        db.execute("ROLLBACK")
        return operator_view("That order or drone is not in the system.")
    if order["status"] != "Pending":
        db.execute("ROLLBACK")
        return operator_view("You can only assign a drone to a pending order.")
    if drone["status"] != "Available":
        db.execute("ROLLBACK")
        return operator_view(
            drone["name"] + " is " + drone["status"] + ", so it cannot take this order."
        )
    other = db.execute(
        """select id from orders
           where drone_id = ? and status in ('Assigned', 'In Transit')""",
        (drone_id,),
    ).fetchone()
    if other:
        db.execute("ROLLBACK")
        return operator_view(drone["name"] + " already has an active order.")
    db.execute(
        "update orders set status = 'Assigned', drone_id = ? where id = ?",
        (drone_id, oid),
    )
    db.execute("update drones set status = 'Assigned' where id = ?", (drone_id,))
    db.execute("COMMIT")
    return operator_view()


## @brief Adds a drone and marks it available.
@app.post("/drones")
def add_drone():
    blocked = need("operator")
    if blocked:
        return blocked
    name = (request.form.get("name") or "").strip()
    station = (request.form.get("station") or "").strip()
    if not name:
        return operator_view("A drone needs a name.")
    taken = get_db().execute("select id from drones where name = ?", (name,)).fetchone()
    if taken:
        return operator_view("A drone with that name already exists.")
    get_db().execute(
        "insert into drones (name, status, station) values (?, 'Available', ?)",
        (name, station),
    )
    return operator_view()


## @brief Sets a drone to available or out of service.
#  A drone that is out on a delivery cannot be changed.
#  @param did The drone id.
@app.post("/drones/<int:did>/status")
def drone_status(did):
    blocked = need("operator")
    if blocked:
        return blocked
    status = request.form.get("drone_status") or ""
    db = get_db()
    db.execute("BEGIN IMMEDIATE")
    drone = db.execute("select * from drones where id = ?", (did,)).fetchone()
    if drone is None:
        db.execute("ROLLBACK")
        return operator_view("That drone is not in the system.")
    if status == drone["status"]:
        db.execute("ROLLBACK")
        return operator_view()
    if status not in ("Available", "Out of Service"):
        db.execute("ROLLBACK")
        return operator_view("Set the drone to Available or Out of Service.")
    active = db.execute(
        """select id from orders
           where drone_id = ? and status in ('Assigned', 'In Transit')""",
        (did,),
    ).fetchone()
    if active:
        db.execute("ROLLBACK")
        return operator_view("That drone is on a delivery. Finish or cancel the order first.")
    db.execute("update drones set status = ? where id = ?", (status, did))
    db.execute("COMMIT")
    return operator_view()


init_db()

if __name__ == "__main__":
    app.run(debug=True)
