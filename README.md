# DroneDash CLE

## Install

Install Python 3.10 or newer. `python` has to work in a terminal.

Install Doxygen from https://www.doxygen.nl/download.html and confirm `doxygen` runs in a terminal.

From this folder, create a `.venv` folder. That folder is a copy of Python used only by this project, so `pip` installs Flask here and not into other classwork.

```text
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt
```

## Run the server

```text
.venv/Scripts/python app.py
```

Open http://127.0.0.1:5000

Operator login: `operator@kent.edu` / `password`

Customers use Create an account on the sign-in page.

Stop the server with Ctrl+C.

The next time you start it, skip the install commands and run `.venv/Scripts/python app.py` again.

## Optional: uv

Skip this section unless you already use uv. It is another way to install the same Python packages and start the same `app.py`.

```text
uv run --with-requirements requirements.txt python app.py
```

## Run Doxygen

From this folder, with the server stopped or left running:

```text
doxygen
```

Open `doxygen-out/html/index.html`.
