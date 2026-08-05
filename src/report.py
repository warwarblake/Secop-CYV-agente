"""
Email rendering and delivery.

HTML is table-based with inline CSS because Gmail, Outlook and Apple Mail
strip <style> blocks and ignore most modern layout. This is deliberately
old-fashioned markup.
"""

from __future__ import annotations

import base64
import html
import os
import pathlib
from datetime import datetime, timedelta, timezone

from . import config

BOGOTA = timezone(timedelta(hours=-5))

# The real CYV logo, extracted directly from Anexo_Obras_CYV_2026.pdf (the
# document Claudia sent) rather than approximated. Encoded as a base64 data
# URI so it's embedded directly in the HTML -- no external image hosting,
# no "click to show images" prompt in the inbox, and it renders identically
# whether the file is actually emailed or just opened locally as preview.html.
_LOGO_PATH = pathlib.Path(__file__).parent.parent / "assets" / "cyv_logo.png"
_BRAND_YELLOW = "#face13"  # sampled directly from the logo's triangle mark


def _logo_data_uri() -> str:
    try:
        data = _LOGO_PATH.read_bytes()
        b64 = base64.b64encode(data).decode("ascii")
        return f"data:image/png;base64,{b64}"
    except FileNotFoundError:
        return ""

PRIORITY_COLORS = {
    "alta": "#2d5016",
    "media": "#d97706",
    "baja": "#64748b",
}


def _cop(value) -> str:
    try:
        return f"${float(value):,.0f} COP"
    except (TypeError, ValueError):
        return "Valor no publicado"


def _date(value) -> str:
    if not value:
        return "No publicada"
    try:
        return datetime.fromisoformat(str(value).replace("Z", "")).strftime("%d/%m/%Y")
    except ValueError:
        return str(value)[:10]


def _days_until_close(row: dict) -> int | None:
    """Returns whole days remaining until the bid deadline, or None if unknown."""
    f = config.FIELDS
    closes_field = f.get("closes")
    if not closes_field:
        return None
    raw = row.get(closes_field)
    if not raw:
        return None
    try:
        closes_dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        if closes_dt.tzinfo is None:
            closes_dt = closes_dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return None
    delta = closes_dt.astimezone(BOGOTA).date() - datetime.now(BOGOTA).date()
    return delta.days


def _closing_note(row: dict) -> tuple[str, str]:
    """
    Returns (countdown_text, color). Countdown reads "Cierra en N dias"
    instead of a bare date, so Claudia doesn't have to do the math herself
    each morning. Falls back to "Verificar en SECOP" when the deadline
    field isn't populated for this row -- never a blank or a guess.

    Color escalates as the deadline approaches: normal text at 8+ days,
    amber inside a week, red inside 3 days. Processes past their deadline
    are already filtered out upstream (secop.filter_not_overdue), but this
    stays defensive against a 0-or-negative edge case rather than assuming.
    """
    days = _days_until_close(row)
    if days is None:
        return "Verificar en SECOP", "#333333"

    f = config.FIELDS
    date_str = _date(row.get(f.get("closes")))

    if days < 0:
        return f"Cierre vencido ({date_str})", "#8a2b2b"
    if days == 0:
        return f"Cierra HOY ({date_str})", "#8a2b2b"
    if days == 1:
        return f"Cierra manana ({date_str})", "#8a2b2b"
    if days <= 3:
        return f"Cierra en {days} dias ({date_str})", "#8a2b2b"
    if days <= 7:
        return f"Cierra en {days} dias ({date_str})", "#8a6d1f"
    return f"Cierra en {days} dias ({date_str})", "#333333"


def _extract_url(value) -> str:
    """
    Socrata columns typed as "URL" (like urlproceso) serialize as a dict --
    typically {"url": "...", "description": "..."} -- not a plain string.
    This normalizes either shape to a plain string.
    """
    if isinstance(value, dict):
        return value.get("url") or value.get("description") or ""
    return value or ""


def _tracking_badge(row: dict) -> str:
    """
    'NUEVO HOY' for a process appearing for the first time, or 'En
    seguimiento desde DD/MM' for one that's been a strong match before and
    is still showing up -- so Claudia can tell continuity from novelty at
    a glance, without it looking like a stale repeat of yesterday's email.
    """
    first_seen = row.get("_first_seen")
    if not first_seen:
        return ""
    today_iso = datetime.now(BOGOTA).date().isoformat()
    if first_seen == today_iso:
        return "NUEVO HOY"
    try:
        d = datetime.fromisoformat(first_seen)
        return f"En seguimiento desde {d.strftime('%d/%m')}"
    except ValueError:
        return ""


def _card(row: dict, rank: int) -> str:
    f = config.FIELDS
    e = html.escape
    priority = row.get("_prioridad", "media")
    color = PRIORITY_COLORS.get(priority, "#6b6b6b")
    badge = _tracking_badge(row)
    closing_text, closing_color = _closing_note(row)

    url = _extract_url(row.get(f["url"]))
    link = (
        f'<a href="{e(url)}" style="color:{_BRAND_YELLOW};text-decoration:none;font-weight:700;font-size:14px;">'
        f"Ver proceso en SECOP II →</a>"
        if url
        else '<span style="color:#999;">Enlace no disponible</span>'
    )

    alert = row.get("_alerta") or ""
    alert_html = (
        f'<tr><td style="padding:12px 0 0 0;font-size:13px;color:#c23636;border-top:1px solid #efe;border-left:3px solid #c23636;padding-left:12px;">'
        f"<strong>Alerta:</strong> {e(alert)}</td></tr>"
        if alert.strip()
        else ""
    )

    return f"""
    <tr><td style="padding:0 0 16px 0;">
      <table width="100%" cellpadding="0" cellspacing="0" style="border-left:5px solid {color};background:#fff;box-shadow:0 1px 3px rgba(0,0,0,0.08);">
        <tr><td style="padding:20px 24px;">
          <table width="100%" cellpadding="0" cellspacing="0">
            <tr>
              <td style="font-size:11px;font-weight:700;color:{color};text-transform:none;">
                #{rank} • Prioridad {e(priority).lower()}{f' • {e(badge)}' if badge else ''}
              </td>
            </tr>
            <tr><td style="padding:8px 0 0 0;font-size:18px;line-height:1.3;font-weight:700;color:#1a1a1a;font-family:Arial,Helvetica,sans-serif;">
              {e(row.get(f['title']) or 'Sin titulo')}
            </td></tr>
            <tr><td style="padding:4px 0 0 0;font-size:12px;color:#666;font-family:Arial,Helvetica,sans-serif;">
              {e(row.get(f['entity']) or 'Entidad no publicada')} • {e(row.get(f['city']) or '')} {f'/ {e(row.get(f["department"] or ""))}' if row.get(f["department"]) else ''}
            </td></tr>
            <tr><td style="padding:14px 0 0 0;">
              <table cellpadding="0" cellspacing="0" style="font-size:12px;color:#333;font-family:Arial,Helvetica,sans-serif;">
                <tr>
                  <td style="padding:0 20px 0 0;"><strong>Valor</strong><br style="line-height:1.3;"><span style="color:#1a1a1a;font-size:13px;font-weight:600;">{_cop(row.get(f['base_price']))}</span></td>
                  <td style="padding:0 20px 0 0;"><strong>Cierre</strong><br style="line-height:1.3;"><span style="color:{closing_color};font-weight:600;font-size:13px;">{e(closing_text)}</span></td>
                  <td><strong>Modalidad</strong><br style="line-height:1.3;"><span style="font-size:13px;">{e(row.get(f['modality']) or 'N/D')}</span></td>
                </tr>
              </table>
            </td></tr>
            <tr><td style="padding:14px 0 0 0;border-top:1px solid #f0f0f0;font-size:13px;line-height:1.6;color:#2a2a2a;font-family:Arial,Helvetica,sans-serif;">
              <strong style="display:block;font-size:11px;color:#1a1a1a;margin-bottom:4px;font-weight:700;">De qué se trata</strong>
              {e(row.get('_resumen') or row.get(f['description']) or '')[:400]}
            </td></tr>

            <tr><td style="padding:14px 0 0 0;font-size:13px;line-height:1.6;color:#2a2a2a;font-family:Arial,Helvetica,sans-serif;">
              <strong style="display:block;font-size:11px;color:#1a1a1a;margin-bottom:4px;font-weight:700;">Por qué encaja</strong>
              {e(row.get('_encaje') or 'Coincide con las líneas de negocio.')}
            </td></tr>

            <tr><td style="padding:14px 0 0 0;font-size:13px;line-height:1.6;color:#2a2a2a;font-family:Arial,Helvetica,sans-serif;">
              <strong style="display:block;font-size:11px;color:#1a1a1a;margin-bottom:4px;font-weight:700;">Experiencia relevante</strong>
              {e(row.get('_proyectos_relacionados') or 'Revisar el pliego de condiciones.')}
            </td></tr>

            {alert_html}
            <tr><td style="padding:14px 0 0 0;">{link}</td></tr>
          </table>
        </td></tr>
      </table>
    </td></tr>
    """


def render(rows: list[dict], stats: dict) -> str:
    today = datetime.now(BOGOTA).strftime("%d de %B de %Y")
    cards = "".join(_card(r, i + 1) for i, r in enumerate(rows))
    logo_uri = _logo_data_uri()

    return f"""<!DOCTYPE html>
<html><body style="margin:0;padding:0;background:#f5f5f5;font-family:Arial,Helvetica,'Trebuchet MS',sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#f5f5f5;padding:24px 12px;">
<tr><td align="center">
<table width="640" cellpadding="0" cellspacing="0" style="max-width:640px;">

  <tr><td style="padding:0 0 24px 0;background:#fff;padding:24px;border-left:5px solid {_BRAND_YELLOW};">
    <table width="100%" cellpadding="0" cellspacing="0">
      <tr>
        <td valign="top" width="100%">
          <div style="font-size:12px;font-weight:700;color:{_BRAND_YELLOW};letter-spacing:0.5px;">
            REPORTE DIARIO
          </div>
          <div style="font-size:28px;font-weight:700;color:#1a1a1a;padding-top:4px;line-height:1.2;">
            Oportunidades<br>Región Caribe
          </div>
          <div style="font-size:13px;color:#666;padding-top:10px;">
            {today}
          </div>
        </td>
        {f'<td valign="middle" align="right" width="110" style="padding-left:16px;"><img src="{logo_uri}" width="100" alt="CYV" style="display:block;border:0;"></td>' if logo_uri else ''}
      </tr>
    </table>
  </td></tr>

  <tr><td style="padding:20px 0 0 0;font-size:13px;line-height:1.8;color:#444;font-family:Arial,Helvetica,sans-serif;">
    <strong>{stats['scanned']} procesos</strong> analizados en los últimos {config.LOOKBACK_DAYS} días. <strong>{stats['candidates']}</strong> clasifican como obra civil por encima de {_cop(config.MIN_BASE_PRICE_COP)}, de los cuales <strong>{stats['new']}</strong> son nuevos. A continuación, los <strong>{len(rows)} mejores</strong> oportunidades.
  </td></tr>

  <tr><td style="padding:16px 0 0 0;">
    {cards}
  </td></tr>

  <tr><td style="padding:20px 0 0 0;font-size:11px;line-height:1.8;color:#666;border-top:1px solid #e0e0e0;padding-top:20px;font-family:Arial,Helvetica,sans-serif;">
    <strong style="color:#1a1a1a;">Fuente:</strong> Datos abiertos de Colombia Compra Eficiente (SECOP II, conjunto {config.DATASET_ID}). Todos los valores, fechas y enlaces provienen directamente del portal oficial. Verifique siempre el pliego de condiciones antes de tomar decisiones.<br>
    <span style="color:#999;margin-top:8px;display:block;padding-top:8px;">CYV Constructora S.A.S. • Licitaciones Región Caribe</span>
  </td></tr>

</table>
</td></tr></table>
</body></html>"""


# ---------------------------------------------------------------------------
# Delivery
# ---------------------------------------------------------------------------

def send(html_body: str, subject: str) -> None:
    """
    Send via Gmail SMTP using an App Password.

    Why Gmail instead of a transactional email API: sending to anyone other
    than your own inbox through a service like Resend requires verifying a
    domain you own via DNS. Gmail SMTP has no such requirement -- it sends
    as you, to anyone, immediately, using an App Password instead of your
    real password. That's the right tradeoff here: this is one email a day,
    not bulk marketing mail, so deliverability-at-scale features don't matter.
    """
    import smtplib
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText

    gmail_address = os.environ["GMAIL_ADDRESS"]
    app_password = os.environ["GMAIL_APP_PASSWORD"]
    to_addrs = [r.strip() for r in os.environ["REPORT_TO"].split(",") if r.strip()]
    cc_addrs = [r.strip() for r in os.environ.get("REPORT_CC", "").split(",") if r.strip()]

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = gmail_address
    msg["To"] = ", ".join(to_addrs)
    if cc_addrs:
        msg["Cc"] = ", ".join(cc_addrs)
    msg.attach(MIMEText(html_body, "html"))

    all_recipients = to_addrs + cc_addrs
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(gmail_address, app_password)
        server.sendmail(gmail_address, all_recipients, msg.as_string())
