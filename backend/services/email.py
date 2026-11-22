"""Email service for sending email verification links."""

from __future__ import annotations

import logging

from backend.config import get_settings

logger = logging.getLogger(__name__)


def generate_verification_url(token: str) -> str:
    settings = get_settings()
    # In development/frontend default runs at http://localhost:3000
    base_url = getattr(settings, "frontend_base_url", "http://localhost:3000")
    return f"{base_url}/verify-email?token={token}"


async def send_verification_email(to_email: str, token: str) -> str:
    """Send email verification link to user email.

    Returns the verification URL for debugging/testing purposes.
    """
    verify_url = generate_verification_url(token)
    # KHONG ghi URL (chua token) ra log. Module nay KHONG gui mail that - email
    # xac minh do Supabase Auth gui (frontend/src/app/register/page.tsx).
    logger.info("[EMAIL SERVICE] verification link generated (not sent by backend)")

    # In production, SMTP code or service API (Resend/SendGrid) can be executed here.
    return verify_url


def generate_password_reset_url(token: str) -> str:
    settings = get_settings()
    base_url = getattr(settings, "frontend_base_url", "http://localhost:3000")
    return f"{base_url}/reset-password?token={token}"


async def send_password_reset_email(to_email: str, token: str) -> str:
    """Send password reset link to user email."""
    reset_url = generate_password_reset_url(token)
    logger.info("[EMAIL SERVICE] password reset link generated (not sent by backend)")
    return reset_url
