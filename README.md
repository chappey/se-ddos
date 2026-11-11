# DroneDash CLE 🚀

Autonomous drone delivery order desk and fleet manager for the greater Cleveland metropolitan area.

---

## ⚡ Quick Start: Choose the ONE option that fits your setup

You do **NOT** need to do all of these! Pick whichever method is easiest for you:

* **[Option 1 (Recommended)](#option-1-easiest--fastest-using-uv--recommended)**: If you use `uv` (zero configuration).
* **[Option 2](#option-2-standard-python--pip)**: Standard Python without a virtual environment.
* **[Option 3](#option-3-using-a-virtual-environment-venv)**: If you prefer using a virtual environment (`.venv`).
* **[Option 4](#option-4-github-codespaces)**: If you are running inside a GitHub Codespace in your web browser.

---

### Option 1: Easiest & Fastest (Using `uv`) — Recommended!

If you have [`uv`](https://docs.astral.sh/uv/) installed:

```bash
uv run app.py
```

*That is literally all! `uv` automatically manages the environment, installs Flask, and starts the web server.*

* To run the automated tests:
  ```bash
  uv run test_orders.py
  ```

---

### Option 2: Standard Python & pip

If you already have Python 3.10+ installed and want to run directly:

1. Open your terminal in this repository folder (`se-ddos`).
2. Install the required dependencies:
   ```bash
   pip install -r requirements.txt
   ```
   *(If `pip` gives an error or is not found, try: `python -m pip install -r requirements.txt` or `python3 -m pip install -r requirements.txt`)*
3. Run the application:
   ```bash
   python app.py
   ```
   *(On Mac or Linux, use `python3 app.py` if `python` defaults to Python 2)*
4. Open [http://127.0.0.1:5000](http://127.0.0.1:5000) in your web browser.

---

### Option 3: Using a Virtual Environment (`.venv`)

A virtual environment keeps packages isolated from your machine's global Python.

#### Step 1: Create the `.venv` folder (Only do this ONCE)
* **Linux / macOS / Kent State `wasp` server**:
  ```bash
  python3 -m venv .venv
  ```
* **Windows (Command Prompt / PowerShell)**:
  ```cmd
  python -m venv .venv
  ```

#### Step 2: Install and Run

> ⚠️ **IMPORTANT**: Windows and Linux/Mac use **different folder names** inside `.venv`!
> * Linux and macOS use `.venv/bin/`
> * Windows uses `.venv\Scripts\`
> If you run `.venv/Scripts/python` on Linux, bash will report: `No such file or directory`.

* **On Linux / macOS / `wasp`**:
  ```bash
  source .venv/bin/activate
  pip install -r requirements.txt
  python app.py
  ```
  *(Or without activating: `.venv/bin/pip install -r requirements.txt` then `.venv/bin/python app.py`)*

* **On Windows (PowerShell or Command Prompt)**:
  ```cmd
  .venv\Scripts\activate
  pip install -r requirements.txt
  python app.py
  ```
  *(Or without activating: `.venv\Scripts\pip install -r requirements.txt` then `.venv\Scripts\python app.py`)*

---

### Option 4: GitHub Codespaces

If you are using a browser-based GitHub Codespace:

1. Look at the bottom panel for the **Terminal** tab.
2. In the terminal, run:
   ```bash
   pip install -r requirements.txt
   python app.py
   ```
3. A popup will appear in the lower-right corner saying **"Your application running on port 5000 is available."** Click **Open in Browser**.

---

## 🔑 Accounts & Testing the App

Once `python app.py` is running, open [http://127.0.0.1:5000](http://127.0.0.1:5000) in your browser.

### 1. Log in as Operator (Fleet Desk)
* **Email**: `operator@kent.edu`
* **Password**: `password`
* **What you can do**: View incoming orders across all Cleveland landing pads, filter orders by delivery status or station, and assign available drones to dispatch deliveries.

### 2. Log in as Customer
* On the login page, click **"Create an account"**.
* Fill out your name, email, and password.
* **What you can do**: Schedule drone delivery orders, select origin and destination pads, specify time windows, and track live status.

### 3. Stop the Server
* In your terminal window, press `Ctrl + C`.

---

## 🧪 Running Automated Tests

Run the test suite anytime to verify that database persistence, order scheduling, validation, and role permissions work:

* **With uv**:
  ```bash
  uv run test_orders.py
  ```
* **With Python**:
  ```bash
  python -m unittest test_orders.py
  ```

---

## ❓ Frequently Asked Questions (Troubleshooting)

#### Q: Why did I get `bash: .venv/Scripts/python: No such file or directory`?
> **Answer**: You are on Linux (e.g. the Kent State `wasp` server) or macOS! Windows uses `.venv/Scripts/`, but Linux/Mac uses `.venv/bin/`.
> To fix: Use `.venv/bin/python app.py`, or simply follow **Option 1 (`uv run app.py`)** or **Option 2 (`python app.py`)**.

#### Q: What is `requirements.txt`?
> **Answer**: It is a plain text file listing the external libraries our project requires (specifically `flask`). Running `pip install -r requirements.txt` instructs Python to fetch and install Flask from the official Python Package Index.

#### Q: What is `pip`?
> **Answer**: `pip` is the package manager built into Python. If your terminal says `pip: command not found`, use `python3 -m pip install -r requirements.txt` (Linux/Mac) or `python -m pip install -r requirements.txt` (Windows).

#### Q: What is `uv`?
> **Answer**: `uv` is a modern, ultra-fast Python package and environment manager. If you use `uv`, you never have to worry about creating venvs or remembering OS paths—running `uv run app.py` handles everything seamlessly in one command.
