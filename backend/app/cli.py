from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import typer
from sqlalchemy.orm import Session

from app.config import get_settings
from app.crypto import hash_password
from app.db import SessionLocal
from app.logging import configure_logging
from app.models import User
from app.services.audit import record_audit
from app.services.backup import create_backup, restore_backup

app = typer.Typer(help="ReceiptVault operator commands. Never prints mailbox tokens or passwords.")


def _db() -> Session:
    return SessionLocal()


@app.command("reset-password")
def reset_password(username: str, password: str):
    """Root-console owner password reset. Logs the action; does not print existing secrets."""
    settings = get_settings()
    configure_logging(settings.log_level)
    db = _db()
    user = db.query(User).filter(User.username == username).one_or_none()
    if not user:
        typer.echo("No such user.")
        raise typer.Exit(1)
    user.password_hash = hash_password(password)
    record_audit(db, event_type="recovery_password_reset", success=True, user_id=user.id, username=username)
    db.commit()
    typer.echo("Password updated. Existing sessions remain valid until expiry or logout-all.")


@app.command("disable-totp")
def disable_totp(username: str):
    settings = get_settings()
    configure_logging(settings.log_level)
    db = _db()
    user = db.query(User).filter(User.username == username).one_or_none()
    if not user:
        typer.echo("No such user.")
        raise typer.Exit(1)
    user.totp_enabled = False
    user.totp_secret_encrypted = None
    record_audit(db, event_type="recovery_totp_disabled", success=True, user_id=user.id, username=username)
    db.commit()
    typer.echo("TOTP disabled for the owner account.")


@app.command("backup")
def backup_cmd(passphrase: str = typer.Option(None), include_evidence: bool = True):
    result = create_backup(get_settings(), passphrase, include_evidence)
    db = _db()
    record_audit(db, event_type="backup", success=True, metadata={"evidence_included": result["evidence_included"]})
    db.commit()
    typer.echo(f"Backup written: {result['path']}")
    typer.echo(f"SHA-256: {result['sha256']}")
    if not result["evidence_included"]:
        typer.echo("WARNING: evidence storage was excluded.")


@app.command("restore")
def restore_cmd(path: Path, passphrase: str = typer.Option(None), dry_run: bool = True, confirm: bool = False):
    if not dry_run and not confirm:
        typer.echo("Refusing restore without --confirm")
        raise typer.Exit(1)
    result = restore_backup(get_settings(), path, passphrase, dry_run=dry_run)
    typer.echo(result)


@app.command("update")
def update_cmd():
    """Download GitHub main into this LXC and restart. Does not use git pull."""
    from app.services.self_update import apply_update, production_install

    if not production_install():
        typer.echo("This command updates /opt/receiptvault inside the LXC.")
        raise typer.Exit(1)
    try:
        result = apply_update()
    except Exception as exc:
        typer.echo(f"Update failed: {exc}")
        raise typer.Exit(1) from exc
    typer.echo(f"Updated to {result['version']}. Hard-refresh the browser.")


@app.command("health")
def health_cmd():
    from sqlalchemy import text

    settings = get_settings()
    db = _db()
    db.execute(text("SELECT 1"))
    typer.echo(f"ReceiptVault {settings.app_version} database=ok at {datetime.now(timezone.utc).isoformat()}")


if __name__ == "__main__":
    app()
