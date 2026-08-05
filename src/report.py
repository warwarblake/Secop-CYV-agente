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
    "alta": "#0f7b3f",
    "media": "#8a6d1f",
    "baja": "#6b6b6b",
}


def _cop(value) -> str:
    try:
        return f"${float(value):,.0f} COP"
    except (TypeError, ValueError):
        return "Valor no publicado"


def _smmlv(value) -> str:
    """
    Base price expressed in SMMLV multiples, which is the unit pliegos use
    for experience and capacity thresholds.

    Real obra publica in these six departments lands between roughly 500 and
    95,000 SMMLV, so this is always formatted as a whole number with a
    thousands separator. One decimal place would be noise at this magnitude.
    """
    try:
        n = float(value) / config.SMMLV_COP
    except (TypeError, ValueError, ZeroDivisionError):
        return ""
    return f"{n:,.0f} SMMLV"


def _apertura_note(row: dict) -> str:
    """
    Scheduled opening of the received bids, falling back to the effective
    opening date when the scheduled one is missing. Returns "" when neither
    is published so the caller can omit the row entirely rather than print
    a blank label.

    This is deliberately NOT labelled "acto administrativo de apertura" --
    that document's date is not in the open dataset (it lives in the pliego).
    Calling it that here would be inventing a data point.
    """
    f = config.FIELDS
    for key in ("opens_responses", "opens_effective"):
        field = f.get(key)
        if not field:
            continue
        raw = row.get(field)
        if raw:
            return _date(raw)
    return ""


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
        # Naive SECOP timestamps are Colombian LOCAL dates, not UTC. Treating
        # them as UTC and converting to Bogota rolled the date back a day, so
        # the countdown ran one day short of the date printed beside it.
        if closes_dt.tzinfo is None:
            closes_dt = closes_dt.replace(tzinfo=BOGOTA)
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
    apertura = _apertura_note(row)
    price_raw = row.get(f["base_price"])
    price_smmlv = _smmlv(price_raw)

    # Publication date of the process. This is NOT the acto administrativo de
    # apertura -- that date is not published in the open dataset and cannot be
    # fetched automatically (the SECOP II process page is CAPTCHA-gated). In
    # practice the acto is issued at or just before publication, so this is the
    # closest true signal available, and it is labelled for what it actually is.
    publicado = _date(row.get(f.get("published")))
    _status_field = f.get("opening_status")
    opening_status = (row.get(_status_field) if _status_field else "") or "N/D"

    url = _extract_url(row.get(f["url"]))
    link = (
        f'<a href="{e(url)}" style="color:#1a5490;text-decoration:none;font-weight:600;">'
        f"Ver proceso en SECOP II &rarr;</a>"
        if url
        else '<span style="color:#999;">Enlace no disponible</span>'
    )

    alert = row.get("_alerta") or ""
    alert_html = (
        f'<tr><td style="padding:8px 0 0 0;font-size:13px;color:#8a2b2b;">'
        f"<strong>Alerta:</strong> {e(alert)}</td></tr>"
        if alert.strip()
        else ""
    )

    return f"""
    <tr><td style="padding:0 0 20px 0;">
      <table width="100%" cellpadding="0" cellspacing="0" style="border:1px solid #e0ddd6;border-left:4px solid {color};background:#ffffff;">
        <tr><td style="padding:18px 20px;">
          <table width="100%" cellpadding="0" cellspacing="0">
            <tr>
              <td style="font-size:12px;letter-spacing:1px;text-transform:uppercase;color:{color};font-weight:700;">
                #{rank} &middot; Prioridad {e(priority)}{f' &middot; {e(badge)}' if badge else ''}
              </td>
            </tr>
            <tr><td style="padding:6px 0 0 0;font-size:17px;line-height:1.35;font-weight:600;color:#1a1a1a;">
              {e(row.get(f['title']) or 'Sin titulo')}
            </td></tr>
            <tr><td style="padding:6px 0 0 0;font-size:13px;color:#555;">
              {e(row.get(f['entity']) or 'Entidad no publicada')}<br>
              {e(row.get(f['city']) or '')}, {e(row.get(f['department']) or '')}
            </td></tr>
            <tr><td style="padding:12px 0 0 0;">
              <table cellpadding="0" cellspacing="0" style="font-size:13px;color:#333;">
                <tr>
                  <td style="padding:3px 24px 3px 0;" valign="top">
                    <strong>Valor base</strong><br>
                    <span style="font-size:15px;color:#1a1a1a;">{_cop(price_raw)}</span>
                  </td>
                  <td style="padding:3px 24px 3px 0;" valign="top">
                    <strong>En SMMLV</strong><br>
                    <span style="font-size:16px;font-weight:700;color:#1a1a1a;">{e(price_smmlv) if price_smmlv else 'N/D'}</span>
                  </td>
                  <td style="padding:3px 0;" valign="top">
                    <strong>Presentaci&oacute;n de ofertas</strong><br>
                    <span style="color:{closing_color};font-weight:600;">{e(closing_text)}</span>
                  </td>
                </tr>
                <tr>
                  <td style="padding:10px 24px 3px 0;" valign="top">
                    <strong>Publicado</strong><br>{e(publicado)}
                  </td>
                  <td style="padding:10px 24px 3px 0;" valign="top">
                    <strong>Apertura de ofertas</strong><br>{e(apertura or 'N/D')}
                  </td>
                  <td style="padding:10px 0 3px 0;" valign="top">
                    <strong>Estado de apertura</strong><br>{e(opening_status)}
                  </td>
                </tr>
                <tr>
                  <td colspan="3" style="padding:10px 0 3px 0;" valign="top">
                    <strong>Modalidad</strong><br>{e(row.get(f['modality']) or 'N/D')}
                  </td>
                </tr>
              </table>
            </td></tr>
            <tr><td style="padding:14px 0 0 0;font-size:14px;line-height:1.55;color:#2a2a2a;">
              <strong style="font-size:11px;letter-spacing:1px;text-transform:uppercase;color:#777;">De que se trata</strong><br>
              {e(row.get('_resumen') or row.get(f['description']) or '')[:400]}
            </td></tr>

            <tr><td style="padding:12px 0 0 0;font-size:14px;line-height:1.55;color:#2a2a2a;">
              <strong style="font-size:11px;letter-spacing:1px;text-transform:uppercase;color:#777;">Por que encaja</strong><br>
              {e(row.get('_encaje') or 'Coincide con las lineas de negocio de la empresa.')}
            </td></tr>

            <tr><td style="padding:12px 0 0 0;font-size:14px;line-height:1.55;color:#2a2a2a;">
              <strong style="font-size:11px;letter-spacing:1px;text-transform:uppercase;color:#777;">Proyectos previos de CYV relacionados</strong><br>
              {e(row.get('_proyectos_relacionados') or 'Sin antecedente directo comparable.')}
            </td></tr>

            {alert_html}
            <tr><td style="padding:14px 0 0 0;font-size:14px;">{link}</td></tr>
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
<html><body style="margin:0;padding:0;background:#f4f2ed;font-family:Georgia,'Times New Roman',serif;">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#f4f2ed;padding:28px 12px;">
<tr><td align="center">
<table width="640" cellpadding="0" cellspacing="0" style="max-width:640px;">

  <tr><td style="padding:0 0 18px 0;">
    <table width="100%" cellpadding="0" cellspacing="0">
      <tr>
        <td valign="top">
          <div style="font-size:11px;letter-spacing:2px;text-transform:uppercase;color:#777;">
            Reporte diario de oportunidades
          </div>
          <div style="font-size:26px;font-weight:700;color:#1a1a1a;padding-top:6px;">
            Licitaciones region Caribe
          </div>
          <div style="font-size:13px;color:#666;padding-top:6px;">
            {today} &middot; Fuente: SECOP II
          </div>
        </td>
        {f'<td valign="top" align="right" width="130"><img src="{logo_uri}" width="120" alt="CYV Constructora" style="display:block;border:0;"></td>' if logo_uri else ''}
      </tr>
    </table>
  </td></tr>

  <tr><td style="height:4px;line-height:4px;font-size:0;background-color:{_BRAND_YELLOW};">&nbsp;</td></tr>

  <tr><td style="padding:20px 0 22px 0;font-size:14px;line-height:1.6;color:#444;">
    Se revisaron <strong>{stats['scanned']}</strong> procesos publicados en los
    ultimos {config.LOOKBACK_DAYS} dias en Atlantico, Bolivar, Magdalena, Sucre,
    Cordoba y Cesar. <strong>{stats['candidates']}</strong> corresponden a obra civil
    por encima de {_cop(config.MIN_BASE_PRICE_COP)}, de los cuales
    <strong>{stats['new']}</strong> son nuevos desde el ultimo reporte.
    A continuacion los {len(rows)} mas relevantes.
  </td></tr>

  {cards}

  <tr><td style="padding:18px 0 0 0;border-top:2px solid {_BRAND_YELLOW};font-size:11px;line-height:1.6;color:#888;">
    Datos obtenidos del portal de datos abiertos de Colombia Compra Eficiente
    (datos.gov.co, conjunto {config.DATASET_ID}). Los valores, fechas y enlaces
    provienen directamente de SECOP II. Verifique siempre el pliego de
    condiciones oficial antes de tomar decisiones.
    <br><br>
    Los valores en SMMLV se calculan sobre un salario minimo de
    {_cop(config.SMMLV_COP)} ({config.SMMLV_YEAR}) y se redondean al entero
    mas cercano. &laquo;Apertura de ofertas&raquo; es la apertura de las
    propuestas recibidas, no el acto administrativo de apertura del proceso:
    esa fecha no se publica en los datos abiertos y debe consultarse en el
    pliego.
    <br><span style="color:#aaa;">Generado para CYV Constructora S.A.S.</span>
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
