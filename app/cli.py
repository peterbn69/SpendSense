"""Flask CLI commands. Like a blueprint: read the input, call a service, report the result."""

import click
from email_validator import EmailNotValidError, validate_email
from flask import Flask, current_app

from app.services import auth, seed
from app.services.auth import PASSWORD_MAX_LENGTH, PASSWORD_MIN_LENGTH

DEFAULT_SEED_EMAIL = "demo@example.com"


def register_commands(app: Flask) -> None:
    app.cli.add_command(seed_command)


@click.command("seed")
@click.option("--email", default=DEFAULT_SEED_EMAIL, show_default=True, help="The user to fill; created if missing.")
@click.option("--months", type=click.IntRange(1, 24), default=seed.DEFAULT_MONTHS, show_default=True,
              help="Completed months of history, plus the current month up to today.")
@click.option("--reset", is_flag=True, help="Delete this user's existing expenses first.")
@click.option("--random-seed", type=int, default=None, help="Fixed seed for repeatable data.")
def seed_command(email: str, months: int, reset: bool, random_seed: int | None) -> None:
    """Fill one user's account with fake expenses (development only)."""
    if not current_app.config.get("ALLOW_SEED"):
        raise click.ClickException("Seeding is turned off in this configuration (set APP_ENV=development).")

    try:
        email = validate_email(email, check_deliverability=False).normalized
    except EmailNotValidError as error:
        raise click.BadParameter(str(error), param_hint="--email") from None

    user = auth.find_by_email(email)
    if user is None:
        password = click.prompt(f"Password for the new user {email}", hide_input=True, confirmation_prompt=True)
        if not PASSWORD_MIN_LENGTH <= len(password) <= PASSWORD_MAX_LENGTH:
            raise click.ClickException(f"Use {PASSWORD_MIN_LENGTH} to {PASSWORD_MAX_LENGTH} characters.")
        user = auth.register(email, password)
        click.echo(f"Created user {user.email}.")

    try:
        added = seed.seed_expenses(user.id, months=months, reset=reset, rng_seed=random_seed)
    except seed.SeedRefusedError as error:
        raise click.ClickException(f"{user.email} already has {error.existing} expenses. Pass --reset to replace them.") from None
    click.echo(f"Added {added} expenses for {user.email}.")
