# SpendSense

A personal expense tracker that shows where your money went this month, forecasts next month, and flags expenses that don't fit your usual pattern.

Built with Python, Flask and PostgreSQL. Server-rendered pages that work without JavaScript; small vanilla-JS scripts make them livelier.

> **Status:** `v1.0.0-rc.1`, feature-complete and hardened. Deployment is the next step.

## Features

- **Log expenses**: amount, category, date and an optional note. Create, read, edit and delete them.
- **Live running total**: as you type an amount, the form shows the month's spending including it (`Spent in November 2026: $3,078.91`). The month follows the date you pick. The landing page has a demo that saves nothing.
- **Dashboard**: this month's total up front, a breakdown by category, and the last 6 months as bar charts.
- **Forecast**: next month's spending per category, as a 3-month moving average of completed months.
- **Unusual expenses**: an expense is flagged when it's far above your other expenses in the same category, measured by a z-score.
- **Category filter** on the expense list. It works as a plain form without JavaScript and filters instantly with it.
- **Accounts**: registration and login. Every user sees only their own data.

## How the numbers work

**Forecast.** Each category's history is the total for every *completed* month (the current, partial month is left out), zero-filled from the month of your first expense. The forecast is the average of the last 3 months, rounded half up to the cent. With fewer than 3 completed months, the dashboard says "Not enough data yet".

**Unusual expenses.** Each expense is compared with your *other* expenses in the same category, so a big outlier can't inflate its own yardstick. It's flagged when its z-score, using the sample standard deviation, is 3 or more. There's no result with fewer than 5 other expenses, or when they are all the same amount. The arithmetic stays in `Decimal` and is exact up to the square root.

Both are pure functions in `app/analytics/`, with no Flask or database, so they're unit-tested directly.

## Tech stack

| Layer | Choice |
|---|---|
| Language | Python 3.15 |
| Web | Flask, Jinja2 templates, Flask-WTF (forms and CSRF), Flask-Login (sessions) |
| Database | PostgreSQL via Flask-SQLAlchemy (SQLAlchemy 2.0 style) and psycopg 3; migrations with Flask-Migrate (Alembic) |
| Security | Argon2 password hashing (`argon2-cffi`), Flask-Limiter on login |
| Front end | Semantic HTML, mobile-first CSS, vanilla JavaScript (no build step, no framework) |
| Server | Gunicorn |
| Tests | pytest against a real PostgreSQL database |

## Architecture

Calls flow one way: **blueprints → services → repositories → models**.

- **Blueprints** (`app/blueprints/`) read the request, call a service, and render or redirect. They never touch the database.
- **Services** (`app/services/`) hold the business rules and own every commit.
- **Repositories** (`app/repositories/`) are the only code that queries the database. Every function that reads or changes expenses takes `user_id`, so another user's expense is simply "not found" (a 404, never a 403).
- **Analytics** (`app/analytics/`) are pure functions for months, forecasts and z-scores, called only by services.

```text
app/
├── analytics/      months.py, forecast.py, anomaly.py: pure functions
├── blueprints/     public, auth, expenses, dashboard: routes and forms
├── repositories/   users.py, expenses.py: all database queries
├── services/       auth, expenses, insights (dashboard), seed
├── static/         css/style.css, js/ (running total, live validation, category filter)
├── templates/      base.html plus pages, partials and error pages
├── categories.py   the fixed category list (key → label)
├── clock.py        "today" and "this month" in APP_TIMEZONE
├── config.py       settings, all read from environment variables
└── models.py       User and Expense
migrations/         Alembic migrations
tests/              pytest suite
wsgi.py             entry point for Gunicorn
```

### Design decisions

- **Money is `Decimal` everywhere**: forms, services, analytics and templates, stored as `NUMERIC(12,2)`. The JavaScript adds amounts as integer cents.
- **One app-wide timezone** (`APP_TIMEZONE`) defines "today" and "this month", always read through `app/clock.py`, so tests can fake time in one place.
- **A fixed category list** in `app/categories.py`, enforced by a database `CHECK` constraint. The database stores the key and pages show the label.
- **Database constraints as the last line of defence**: positive amounts, known categories, lowercase emails, cascading deletes, and an index on `(user_id, spent_on)`.
- **Progressive enhancement**: every page works without JavaScript. The scripts read their data, and even their validation messages, from `data-` attributes the server writes, so the browser hints say exactly what the server would.

## Getting started

The commands below are for Windows PowerShell. On macOS or Linux, activate the environment with `source .venv/bin/activate`.

### 1. Prerequisites

- Python 3.15
- PostgreSQL, with two empty databases: one for development and a separate, disposable one for the tests. For example, in `psql`:

  ```sql
  CREATE USER spendsense WITH PASSWORD 'choose-a-password';
  CREATE DATABASE spendsense OWNER spendsense;
  CREATE DATABASE spendsense_test OWNER spendsense;
  ```

### 2. Install

```powershell
git clone https://github.com/peterbn69/SpendSense.git
cd SpendSense
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
```

### 3. Configure

Copy the example settings and fill them in. `.env` is git-ignored.

```powershell
Copy-Item .env.example .env
```

| Variable | Required | Meaning |
|---|---|---|
| `SECRET_KEY` | Yes | Signs session cookies. At least 32 characters in production. Generate one with `python -c "import secrets; print(secrets.token_hex(32))"` |
| `DATABASE_URL` | Yes | `postgresql+psycopg://USER:PASSWORD@HOST:5432/DBNAME` |
| `APP_TIMEZONE` | Yes | IANA timezone for "today", e.g. `America/Toronto` |
| `APP_ENV` | No | `production` (default), `development` or `testing` |
| `FLASK_DEBUG` | No | `1` turns on the debugger in development; keep `0` anywhere else |
| `LOG_LEVEL` | No | `DEBUG`, `INFO` (default), `WARNING`, `ERROR` or `CRITICAL` |
| `TEST_DATABASE_URL` | For tests | A separate database; the tests drop and recreate its tables |

For local development, set `APP_ENV=development` (and `FLASK_DEBUG=1` if you want the debugger).

### 4. Create the tables and run

```powershell
flask db upgrade
flask run
```

Then open <http://localhost:5000>.

To try the dashboard, forecast and flags with realistic data, fill an account with 6 months of fake expenses. This only works in development, and it asks for a password if the account is new:

```powershell
flask seed
```

`flask seed --help` lists its options (`--email`, `--months`, `--reset`, `--random-seed`).

## Tests

```powershell
pytest
```

The suite runs against PostgreSQL, not SQLite, so the database's `CHECK` constraints are exercised too. It covers, among other things:

- **Data isolation:** user B gets a 404 for every one of user A's expense IDs.
- **Bad input:** every form is fed blank, negative, enormous, non-numeric and hostile input, and none of it produces a 500.
- **Time:** "today" is judged in the app's timezone, with time faked through `app/clock.py`.
- **Analytics:** edge cases for the forecast (fewer than 3 months) and the z-score (fewer than 5 points, a standard deviation of 0).
- **Security:** CSRF checks, the login rate limit, the production config (debug off, secure cookies) and security headers.

## Security

- Passwords are hashed with Argon2. A failed login shows one generic message, and a check for an email that doesn't exist takes as long as a real one.
- Every form has server-side validation and a CSRF token, logout and delete included.
- Session cookies are HttpOnly and SameSite=Lax, and Secure in production. Debug is never on in the production config.
- The `next` redirect after login only goes to pages on this site.
- Login attempts are limited to 5 per minute and 20 per hour per IP.
- No secrets in the code or in git: every setting comes from environment variables.
- Logs record failed logins by IP only, never the email that was typed.

## Production

Run the app with Gunicorn on a Linux host, with every setting in environment variables and `APP_ENV=production`, and run migrations on every deploy:

```bash
flask db upgrade
gunicorn wsgi:app
```

Gunicorn doesn't run natively on Windows; use `flask run` there for development.

## License

[MIT](LICENSE) © 2026 Bao Nguyen
