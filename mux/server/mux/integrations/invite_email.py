"""Invite emails through Supabase Auth (its own mailer, so no SMTP setup).

New addresses get Supabase's invite email; Supabase won't invite an address that already has an account,
so those get a magic sign-in link instead. Both land on /auth/callback?next=/room/<id>, which signs the
person in and opens the room, where joining matches their email to the pending invite.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional
from urllib.parse import quote

import httpx

from mux.config import settings

logger = logging.getLogger(__name__)


@dataclass
class EmailResult:
    sent: bool
    error: Optional[str] = None


def room_link(room_id: str) -> str:
    return f"{settings.web_app_url.rstrip('/')}/room/{room_id}"


def _redirect_to(room_id: str) -> str:
    return f"{settings.web_app_url.rstrip('/')}/auth/callback?next={quote(f'/room/{room_id}', safe='')}"


def _already_registered(response: httpx.Response) -> bool:
    if response.status_code not in (400, 422):
        return False
    try:
        body = response.json()
    except ValueError:
        return False
    text = f"{body.get('error_code', '')} {body.get('code', '')} {body.get('msg', '')} {body.get('message', '')}".lower()
    return "email_exists" in text or "already" in text


def _error(response: httpx.Response) -> str:
    try:
        body = response.json()
        message = body.get("msg") or body.get("message") or body.get("error_description") or body.get("error")
    except ValueError:
        message = None
    if response.status_code == 429:
        return "Supabase's email limit was reached; try again later or send the link yourself"
    return f"Supabase refused the email ({response.status_code}{': ' + message if message else ''})"


async def send_invite_email(email: str, room_id: str, room_title: str, inviter_name: Optional[str]) -> EmailResult:
    """Email `email` a link into the room. Never raises: the invite is saved whether or not this works."""
    if not settings.supabase_url or not settings.supabase_service_role_key:
        return EmailResult(False, "Email isn't set up on the server (SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY)")

    base = settings.supabase_url.rstrip("/") + "/auth/v1"
    key = settings.supabase_service_role_key
    headers = {"apikey": key, "Authorization": f"Bearer {key}"}
    params = {"redirect_to": _redirect_to(room_id)}
    # Available to the email templates as {{ .Data.room_title }} etc.
    data = {"room_id": room_id, "room_title": room_title, "invited_by": inviter_name or ""}

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(f"{base}/invite", params=params, headers=headers, json={"email": email, "data": data})
            if r.is_success:
                return EmailResult(True)
            if not _already_registered(r):
                logger.warning(f"Invite email to room {room_id} failed: {r.status_code} {r.text[:200]}")
                return EmailResult(False, _error(r))
            # Existing account: a magic sign-in link instead (create_user false: never makes an account here)
            r = await client.post(f"{base}/otp", params=params, headers=headers, json={"email": email, "create_user": False})
            if r.is_success:
                return EmailResult(True)
            logger.warning(f"Sign-in email to room {room_id} failed: {r.status_code} {r.text[:200]}")
            return EmailResult(False, _error(r))
    except httpx.HTTPError as e:
        logger.warning(f"Could not reach Supabase to send an invite email: {e}")
        return EmailResult(False, "Could not reach Supabase to send the email")
