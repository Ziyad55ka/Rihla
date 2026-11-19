import asyncio
import logging
import smtplib
import ssl
from contextlib import asynccontextmanager
from email.message import EmailMessage
from email.utils import formatdate

import httpx2 as httpx
from fastapi import FastAPI

from app.core.config import Settings
from app.services.generation_inputs import (
    TripEmail,
    claim_trip_email,
    finish_trip_email,
    private_rpc_configured,
)

logger = logging.getLogger(__name__)


def send_gmail(job: TripEmail, settings: Settings, subject: str, text: str) -> str:
    message = EmailMessage()
    message["From"] = settings.gmail_address
    message["To"] = job.email
    message["Subject"] = subject
    message["Date"] = formatdate(localtime=False)
    message["Message-ID"] = f"<rihla-trip-{job.id}@gmail.com>"
    message.set_content(text)
    smtp = None
    try:
        smtp = smtplib.SMTP_SSL(
            "smtp.gmail.com", 465, timeout=10, context=ssl.create_default_context()
        )
        smtp.login(settings.gmail_address, "".join(settings.gmail_app_password.split()))
        smtp.send_message(message)
        return "sent"
    except smtplib.SMTPRecipientsRefused as error:
        return (
            "retry"
            if any(code < 500 for code, _ in error.recipients.values())
            else "failed"
        )
    except smtplib.SMTPAuthenticationError:
        return "retry"
    except smtplib.SMTPResponseException as error:
        return "retry" if error.smtp_code < 500 else "failed"
    except (OSError, smtplib.SMTPException):
        return "retry"
    finally:
        if smtp is not None:
            # Once DATA is accepted, a disconnect during cleanup must not resend it.
            smtp.close()


async def send_trip_email(
    job: TripEmail, settings: Settings, client: httpx.AsyncClient
) -> str:
    trip_url = f"{settings.trip_app_url.rstrip('/')}/trips/{job.trip_id}"
    if job.proposal_id:
        subject = "تحدّث مقترح الرحلة | Trip proposal updated"
        text = (
            "حُفظت نسخة جديدة من مقترح رحلتكم. افتح المقترح لمراجعة التعديل.\n"
            "A revised proposal is ready. Open it to review the latest version.\n"
            f"{trip_url}/proposals/{job.proposal_id}\n\n"
            f"الرحلة | Trip: {trip_url}"
        )
    else:
        subject = "مقترحات رحلتكم جاهزة | Trip proposals ready"
        text = (
            "مقترحات رحلتكم جاهزة. افتح الرحلة للاطلاع على الخيارات.\n"
            "Your trip proposals are ready. Open the trip to review your options.\n"
            f"{trip_url}"
        )
    if settings.trip_email_provider == "gmail":
        return await asyncio.to_thread(send_gmail, job, settings, subject, text)
    try:
        response = await client.post(
            "https://api.resend.com/emails",
            headers={
                "Authorization": f"Bearer {settings.resend_api_key}",
                "Idempotency-Key": f"rihla-trip-email/{job.id}",
            },
            json={
                "from": settings.trip_email_from,
                "to": [job.email],
                "subject": subject,
                "text": text,
            },
        )
    except httpx.RequestError:
        return "retry"
    if response.is_success:
        return "sent"
    # Resend returns concurrent_idempotent_requests if another worker is
    # still waiting on the same submission. A changed payload is permanent.
    if response.status_code == 409:
        return (
            "retry" if "concurrent_idempotent_requests" in response.text else "failed"
        )
    if response.status_code in {401, 403, 408, 429} or response.status_code >= 500:
        return "retry"
    return "failed"


async def deliver_trip_emails(settings: Settings) -> None:
    async with httpx.AsyncClient(timeout=12, trust_env=False) as client:
        while True:
            delay = 15
            try:
                job = await claim_trip_email(settings)
                if job:
                    outcome = await send_trip_email(job, settings, client)
                    await finish_trip_email(job, outcome, settings)
                    if outcome != "sent":
                        logger.warning("Trip email %s: %s", job.id, outcome)
                    delay = 1
            except Exception:
                # A lease expires if acknowledgment fails. Avoid logging addresses,
                # provider responses or credentials, and keep the worker available.
                logger.warning("Trip email queue unavailable; retrying")
            await asyncio.sleep(delay)


@asynccontextmanager
async def email_lifespan(app: FastAPI):
    settings = app.state.settings
    if not settings.trip_emails_enabled:
        yield
        return
    provider_ready = (
        settings.gmail_address and settings.gmail_app_password
        if settings.trip_email_provider == "gmail"
        else settings.trip_email_from and settings.resend_api_key
    )
    if not all(
        (
            settings.trip_app_url,
            provider_ready,
            private_rpc_configured(settings),
        )
    ):
        logger.error(
            "Trip email delivery is paused because required settings are missing"
        )
        yield
        return
    worker = asyncio.create_task(deliver_trip_emails(settings))
    try:
        yield
    finally:
        worker.cancel()
        await asyncio.gather(worker, return_exceptions=True)
