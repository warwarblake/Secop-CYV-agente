"""
Email rendering and delivery.

HTML is table-based with inline CSS because Gmail, Outlook and Apple Mail
strip <style> blocks and ignore most modern layout. This is deliberately
old-fashioned markup.
"""

from __future__ import annotations

import html
import os
from datetime import datetime, timedelta, timezone

from . import config

BOGOTA = timezone(timedelta(hours=-5))

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


def _date(value) -> str:
    if not value:
        return "No publicada"
    try:
        return datetime.fromisoformat(str(value).replace("Z", "")).strftime("%d/%m/%Y")
    except ValueError:
        return str(value)[:10]


def _closing_note(row: dict) -> str:
    """
    Returns the real bid-submission deadline once config.FIELDS['closes'] is
    mapped and populated for this row. Until then, points to the SECOP page
    directly rather than showing a blank or fabricated date.
    """
    f = config.FIELDS
    closes_field = f.get("closes")
    if closes_field and row.get(closes_field):
        return _date(row.get(closes_field))
    return "Verificar en SECOP"


def _card(row: dict, rank: int) -> str:
    f = config.FIELDS
    e = html.escape
    priority = row.get("_prioridad", "media")
    color = PRIORITY_COLORS.get(priority, "#6b6b6b")

    url = row.get(f["url"]) or ""
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
                #{rank} &middot; Prioridad {e(priority)}
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
                  <td style="padding:3px 24px 3px 0;"><strong>Valor base</strong><br>{_cop(row.get(f['base_price']))}</td>
                  <td style="padding:3px 24px 3px 0;"><strong>Presentaci&oacute;n de ofertas (fecha l&iacute;mite)</strong><br>{e(_closing_note(row))}</td>
                  <td style="padding:3px 0;"><strong>Modalidad</strong><br>{e(row.get(f['modality']) or 'N/D')}</td>
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

            <tr><td style="padding:12px 0 0 0;">
              <table width="100%" cellpadding="0" cellspacing="0" style="background:#f7f4ec;border:1px dashed #d6cfbc;">
                <tr><td style="padding:12px;font-size:13px;line-height:1.55;color:#4a4335;">
                  <strong style="font-size:11px;letter-spacing:1px;text-transform:uppercase;color:#8a7a4f;">
                    Experiencia probable &middot; ESTIMACION
                  </strong><br>
                  {e(row.get('_experiencia') or 'Requiere revisar el pliego.')}
                  <br><span style="color:#8a7a4f;font-style:italic;">
                    No es un dato publicado. Confirmar en el pliego de condiciones.
                  </span>
                </td></tr>
              </table>
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

    return f"""<!DOCTYPE html>
<html><body style="margin:0;padding:0;background:#f4f2ed;font-family:Georgia,'Times New Roman',serif;">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#f4f2ed;padding:28px 12px;">
<tr><td align="center">
<table width="640" cellpadding="0" cellspacing="0" style="max-width:640px;">

  <tr><td style="padding:0 0 22px 0;border-bottom:2px solid #1a1a1a;">
    <div style="font-size:11px;letter-spacing:2px;text-transform:uppercase;color:#777;">
      Reporte diario de oportunidades
    </div>
    <div style="font-size:26px;font-weight:700;color:#1a1a1a;padding-top:6px;">
      Licitaciones region Caribe
    </div>
    <div style="font-size:13px;color:#666;padding-top:6px;">
      {today} &middot; Fuente: SECOP II
    </div>
  </td></tr>

  <tr><td style="padding:20px 0 22px 0;font-size:14px;line-height:1.6;color:#444;">
    Se revisaron <strong>{stats['scanned']}</strong> procesos publicados en los
    ultimos {config.LOOKBACK_DAYS} dias en Atlantico, Bolivar, Magdalena, Sucre,
    Cordoba y Cesar. <strong>{stats['candidates']}</strong> corresponden a obra civil
    por encima de {_cop(config.MIN_BASE_PRICE_COP)}, de los cuales
    <strong>{stats['new']}</strong> son nuevos desde el ultimo reporte.
    A continuacion los {len(rows)} mas relevantes.
  </td></tr>

  {cards}

  <tr><td style="padding:18px 0 0 0;border-top:1px solid #ddd9d0;font-size:11px;line-height:1.6;color:#888;">
    Datos obtenidos del portal de datos abiertos de Colombia Compra Eficiente
    (datos.gov.co, conjunto {config.DATASET_ID}). Los valores, fechas y enlaces
    provienen directamente de SECOP II. Verifique siempre el pliego de
    condiciones oficial antes de tomar decisiones.
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
