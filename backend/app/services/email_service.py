import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from aiosmtplib import SMTP

from ..config import SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS, SMTP_FROM

logger = logging.getLogger(__name__)


def _smtp_configured() -> bool:
    return bool(SMTP_HOST and SMTP_USER)


async def send_email(to: str, subject: str, html_body: str) -> bool:
    if not _smtp_configured():
        logger.warning("SMTP not configured — skipping email to %s", to)
        return False

    msg = MIMEMultipart("alternative")
    msg["From"] = SMTP_FROM
    msg["To"] = to
    msg["Subject"] = subject
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    try:
        smtp = SMTP(
            hostname=SMTP_HOST,
            port=SMTP_PORT,
            start_tls=True,
        )
        async with smtp:
            await smtp.login(SMTP_USER, SMTP_PASS)
            await smtp.send_message(msg)
        logger.info("Email sent to %s: %s", to, subject)
        return True
    except Exception:
        logger.exception("Failed to send email to %s", to)
        return False


async def send_password_reset_email(email: str, reset_url: str) -> bool:
    html = f"""
    <div style="max-width:480px;margin:0 auto;font-family:system-ui,sans-serif;color:#333">
      <h2 style="color:#2563eb">HKMU Campus — Password Reset</h2>
      <p>We received a request to reset your password. Click the button below to set a new one:</p>
      <p style="text-align:center;margin:24px 0">
        <a href="{reset_url}" style="background:#2563eb;color:#fff;padding:12px 28px;border-radius:8px;text-decoration:none;font-weight:600">
          Reset Password
        </a>
      </p>
      <p style="color:#666;font-size:14px">
        This link expires in <strong>1 hour</strong>. If you didn't request this, you can safely ignore this email.
      </p>
    </div>
    """
    return await send_email(email, "HKMU Campus — Reset Your Password", html)


async def send_verification_email(email: str, verify_url: str) -> bool:
    html = f"""
    <div style="max-width:480px;margin:0 auto;font-family:system-ui,sans-serif;color:#333">
      <h2 style="color:#2563eb">HKMU Campus — Verify Your Email</h2>
      <p>Welcome! Please verify your email address by clicking below:</p>
      <p style="text-align:center;margin:24px 0">
        <a href="{verify_url}" style="background:#2563eb;color:#fff;padding:12px 28px;border-radius:8px;text-decoration:none;font-weight:600">
          Verify Email
        </a>
      </p>
      <p style="color:#666;font-size:14px">
        This link expires in <strong>24 hours</strong>.
      </p>
    </div>
    """
    return await send_email(email, "HKMU Campus — Verify Your Email", html)
