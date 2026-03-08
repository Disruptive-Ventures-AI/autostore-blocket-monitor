import asyncio
import json
import logging
from datetime import datetime, timezone, timedelta
from functools import partial

import resend

from app.config import (
    EMAIL_BATCH_DELAY_S,
    EMAIL_BATCH_SIZE,
    EMAIL_FROM,
    EMAIL_RECIPIENTS,
    EMPTY_EMAIL_THROTTLE_HOURS,
    RESEND_API_KEY,
)
from app.database import get_run_state, set_run_state
from app.models import Car

logger = logging.getLogger(__name__)

resend.api_key = RESEND_API_KEY


def _format_mileage(car: Car) -> str:
    if car.mileage_raw is None:
        return "Okänd"
    try:
        raw_val = int(car.mileage_raw)
    except (ValueError, TypeError):
        return str(car.mileage_raw)
    if raw_val < 1_000:
        return f"{raw_val} mil ({raw_val * 10} km)"
    return f"{raw_val} km"


def _format_price(price: int | None) -> str:
    if price is None:
        return "Pris saknas"
    return f"{price:,} kr".replace(",", " ")


def _car_card_html(car: Car) -> str:
    priority_badge = ""
    if car.is_priority:
        priority_badge = (
            '<span style="display:inline-block;background:#F5A623;color:white;'
            'padding:2px 8px;border-radius:4px;font-size:11px;font-weight:bold;'
            'margin-left:8px;">PRIORITET</span>'
        )

    thumbnail_html = ""
    if car.thumbnail:
        thumbnail_html = (
            f'<img src="{car.thumbnail}" alt="" '
            f'style="width:120px;height:90px;object-fit:cover;border-radius:6px;'
            f'margin-right:15px;flex-shrink:0;" />'
        )

    return f"""
    <div style="background:white;border-radius:10px;box-shadow:0 2px 8px rgba(0,0,0,0.08);
                padding:15px;margin-bottom:12px;display:flex;align-items:flex-start;">
        {thumbnail_html}
        <div style="flex:1;">
            <div style="margin-bottom:6px;">
                <a href="{car.url}" style="color:#333;text-decoration:none;font-weight:bold;font-size:15px;">
                    {car.car_title}
                </a>
                {priority_badge}
            </div>
            <div style="color:#666;font-size:13px;line-height:1.6;">
                <strong>Pris:</strong> {_format_price(car.price)} &nbsp;|&nbsp;
                <strong>År:</strong> {car.year or 'Okänt'} &nbsp;|&nbsp;
                <strong>Mil:</strong> {_format_mileage(car)}<br/>
                <strong>Bränsle:</strong> {car.fuel or 'Okänt'} &nbsp;|&nbsp;
                <strong>Växellåda:</strong> {car.gearbox or 'Okänt'} &nbsp;|&nbsp;
                <strong>Plats:</strong> {car.location or 'Okänd'}
            </div>
        </div>
    </div>"""


def _priority_summary_html(priority_cars: list[Car]) -> str:
    if not priority_cars:
        return ""

    rows = ""
    for car in priority_cars:
        rows += f"""
            <tr>
                <td style="padding:6px 10px;border-bottom:1px solid #eee;">
                    <a href="{car.url}" style="color:#333;text-decoration:none;font-weight:600;font-size:13px;">{car.car_title}</a>
                </td>
                <td style="padding:6px 10px;border-bottom:1px solid #eee;font-size:13px;white-space:nowrap;">{_format_price(car.price)}</td>
                <td style="padding:6px 10px;border-bottom:1px solid #eee;font-size:13px;white-space:nowrap;">{car.year or '—'}</td>
                <td style="padding:6px 10px;border-bottom:1px solid #eee;font-size:13px;white-space:nowrap;">{_format_mileage(car)}</td>
                <td style="padding:6px 10px;border-bottom:1px solid #eee;font-size:13px;white-space:nowrap;">{car.location or '—'}</td>
            </tr>"""

    return f"""
    <div style="background:white;border-radius:10px;box-shadow:0 2px 8px rgba(0,0,0,0.08);
                padding:18px;margin-bottom:20px;border-left:4px solid #F5A623;">
        <h2 style="margin:0 0 12px;font-size:16px;color:#333;">
            <span style="color:#F5A623;">&#9660;</span> Transport &amp; Pickup — {len(priority_cars)} fordon
        </h2>
        <table style="width:100%;border-collapse:collapse;">
            <thead>
                <tr style="background:#f9f9f9;">
                    <th style="padding:6px 10px;text-align:left;font-size:12px;color:#888;font-weight:600;">Fordon</th>
                    <th style="padding:6px 10px;text-align:left;font-size:12px;color:#888;font-weight:600;">Pris</th>
                    <th style="padding:6px 10px;text-align:left;font-size:12px;color:#888;font-weight:600;">År</th>
                    <th style="padding:6px 10px;text-align:left;font-size:12px;color:#888;font-weight:600;">Mil</th>
                    <th style="padding:6px 10px;text-align:left;font-size:12px;color:#888;font-weight:600;">Plats</th>
                </tr>
            </thead>
            <tbody>
                {rows}
            </tbody>
        </table>
    </div>"""


def _build_html(cars: list[Car], batch_num: int = 0, total_batches: int = 0) -> str:
    priority_cars = [c for c in cars if c.is_priority]
    regular_cars = [c for c in cars if not c.is_priority]
    sorted_cars = priority_cars + regular_cars

    overview = (
        f"<p style='color:#555;font-size:14px;'>"
        f"Hittade <strong>{len(cars)}</strong> nya bilar"
    )
    if priority_cars:
        overview += (
            f" varav <strong style='color:#F5A623;'>{len(priority_cars)} "
            f"transport/pickup</strong> och <strong>{len(regular_cars)} personbilar</strong>"
        )
    overview += ".</p>"

    priority_summary = _priority_summary_html(priority_cars)
    cards = "\n".join(_car_card_html(c) for c in sorted_cars)

    batch_info = ""
    if total_batches > 1:
        batch_info = f" (Del {batch_num}/{total_batches})"

    return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"/></head>
<body style="margin:0;padding:0;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:#f5f5f5;">
    <div style="max-width:650px;margin:0 auto;padding:20px;">
        <div style="background:linear-gradient(135deg,#667EEA 0%,#764BA2 100%);
                    border-radius:12px;padding:25px 30px;margin-bottom:20px;color:white;">
            <h1 style="margin:0;font-size:22px;">Nya Privatannonser{batch_info}</h1>
            <p style="margin:5px 0 0;opacity:0.9;font-size:14px;">Autostore Sverige AB — Automatisk bilsökning</p>
        </div>
        {overview}
        {priority_summary}
        {cards}
        <div style="text-align:center;padding:20px 0;color:#999;font-size:12px;">
            Autostore Sverige AB — Automatisk bilsökning
        </div>
    </div>
</body>
</html>"""


def _build_empty_html() -> str:
    return """<!DOCTYPE html>
<html>
<head><meta charset="utf-8"/></head>
<body style="margin:0;padding:0;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:#f5f5f5;">
    <div style="max-width:650px;margin:0 auto;padding:20px;">
        <div style="background:linear-gradient(135deg,#667EEA 0%,#764BA2 100%);
                    border-radius:12px;padding:25px 30px;margin-bottom:20px;color:white;">
            <h1 style="margin:0;font-size:22px;">Bilsökning</h1>
            <p style="margin:5px 0 0;opacity:0.9;font-size:14px;">Autostore Sverige AB — Automatisk bilsökning</p>
        </div>
        <p style="color:#555;font-size:14px;">Inga nya bilar hittades denna körning.</p>
        <div style="text-align:center;padding:20px 0;color:#999;font-size:12px;">
            Autostore Sverige AB — Automatisk bilsökning
        </div>
    </div>
</body>
</html>"""


async def _send_email(subject: str, html: str) -> None:
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(
        None,
        partial(
            resend.Emails.send,
            {
                "from": EMAIL_FROM,
                "to": EMAIL_RECIPIENTS,
                "subject": subject,
                "html": html,
            },
        ),
    )


async def send_car_emails(cars: list[Car]) -> None:
    if not cars:
        await _send_empty_email()
        return

    batches = [
        cars[i : i + EMAIL_BATCH_SIZE]
        for i in range(0, len(cars), EMAIL_BATCH_SIZE)
    ]
    total = len(batches)
    total_cars = len(cars)

    for idx, batch in enumerate(batches, 1):
        if total > 1:
            subject = f"Nya Privatannonser -- {total_cars} bilar (Del {idx}/{total})"
        else:
            subject = f"Nya Privatannonser -- {total_cars} bilar"

        html = _build_html(batch, idx, total)
        await _send_email(subject, html)
        logger.info(json.dumps({
            "event": "email_sent",
            "batch": idx,
            "total_batches": total,
            "cars_in_batch": len(batch),
        }))

        if idx < total:
            await asyncio.sleep(EMAIL_BATCH_DELAY_S)


async def _send_empty_email() -> None:
    last_empty = await get_run_state("last_empty_email")
    now = datetime.now(timezone.utc)

    if last_empty:
        try:
            last_dt = datetime.fromisoformat(last_empty)
            if now - last_dt < timedelta(hours=EMPTY_EMAIL_THROTTLE_HOURS):
                logger.info(json.dumps({"event": "empty_email_throttled"}))
                return
        except ValueError:
            pass

    await _send_email("Bilsokning -- Inga nya bilar", _build_empty_html())
    await set_run_state("last_empty_email", now.isoformat())
    logger.info(json.dumps({"event": "empty_email_sent"}))
