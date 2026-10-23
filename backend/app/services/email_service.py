from __future__ import annotations
import httpx
from app.core.config import get_settings

BREVO_API_URL = "https://api.brevo.com/v3/smtp/email"

async def send_otp_email(to_email: str, otp_code: str) -> tuple[bool, str]:
    settings = get_settings()
    api_key = (settings.brevo_api_key or "").strip().strip('"').strip("'")
    if not api_key:
        print("[EMAIL WARNING] BREVO_API_KEY is not configured.")
        return False, "BREVO_API_KEY is not configured" 

    sender_email = (settings.brevo_sender_email or "noreply@migrationstudio.ai").strip().strip('"').strip("'")
    sender_name = (settings.brevo_sender_name or "Migration Factory").strip().strip('"').strip("'")

    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
      <meta charset="utf-8">
      <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #0b0f19; color: #f1f5f9; padding: 40px 20px; }}
        .card {{ max-width: 500px; margin: 0 auto; background: #161e2e; border: 1px solid #2d3748; border-radius: 12px; padding: 32px; box-shadow: 0 10px 25px rgba(0,0,0,0.5); }}
        .badge {{ display: inline-block; background: #3b82f6; color: #fff; font-weight: 700; font-size: 14px; padding: 4px 10px; border-radius: 6px; margin-bottom: 16px; }}
        h1 {{ font-size: 22px; margin-top: 0; color: #ffffff; }}
        p {{ font-size: 15px; color: #94a3b8; line-height: 1.6; }}
        .otp-box {{ background: #1e293b; border: 2px dashed #3b82f6; border-radius: 8px; font-size: 32px; font-weight: 800; letter-spacing: 8px; text-align: center; color: #60a5fa; padding: 18px; margin: 24px 0; }}
        .footer {{ font-size: 12px; color: #64748b; margin-top: 24px; border-top: 1px solid #2d3748; padding-top: 16px; text-align: center; }}
      </style>
    </head>
    <body>
      <div class="card">
        <div class="badge">Migration Factory</div>
        <h1>Your Registration Verification Code</h1>
        <p>Welcome to Migration AI Studio. Please use the following 6-digit verification code to complete your registration and set up your password.</p>
        <div class="otp-box">{otp_code}</div>
        <p>This code will expire in <strong>10 minutes</strong>. If you did not request this registration, you can safely ignore this email.</p>
        <div class="footer">
          &copy; 2026 Migration AI Studio. All rights reserved.
        </div>
      </div>
    </body>
    </html>
    """

    payload = {
        "sender": {"name": sender_name, "email": sender_email},
        "to": [{"email": to_email}],
        "subject": f"Your Migration Factory Verification Code: {otp_code}",
        "htmlContent": html_content,
    }

    headers = {
        "accept": "application/json",
        "api-key": api_key,
        "content-type": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(BREVO_API_URL, json=payload, headers=headers)
            if resp.status_code in (200, 201, 202):
                print(f"[EMAIL SUCCESS] OTP email sent to {to_email}")
                return True, "Email sent successfully"
            else:
                print(f"[EMAIL ERROR] Brevo API status {resp.status_code}: {resp.text}")
                return False, resp.text
    except Exception as e:
        print(f"[EMAIL EXCEPTION] Failed to send email to {to_email}: {e}")
        return False, str(e)


async def send_migration_schedule_digest(to_email: str, project_name: str, summary: dict) -> tuple[bool, str]:
    settings = get_settings()
    api_key = (settings.brevo_api_key or "").strip().strip('"').strip("'")
    if not api_key:
        print("[EMAIL WARNING] BREVO_API_KEY is not configured.")
        return False, "BREVO_API_KEY is not configured"

    sender_email = (settings.brevo_sender_email or "noreply@migrationstudio.ai").strip().strip('"').strip("'")
    sender_name = (settings.brevo_sender_name or "Migration Factory").strip().strip('"').strip("'")

    status = summary.get("status", "SUCCESS")
    total_delta = summary.get("total_delta_rows", 0)
    tables = summary.get("tables", [])
    duration_sec = summary.get("duration_seconds", 0)
    executed_at = summary.get("executed_at", "")

    status_color = "#10b981" if status == "SUCCESS" else "#ef4444"
    status_badge = f'<span style="background: {status_color}; color: #fff; font-weight: bold; padding: 4px 10px; border-radius: 4px;">{status}</span>'

    table_rows_html = ""
    for t in tables:
        t_status_color = "#10b981" if t.get("status") == "PASSED" else "#ef4444"
        table_rows_html += f"""
        <tr style="border-bottom: 1px solid #334155;">
            <td style="padding: 10px 12px; color: #f1f5f9; font-weight: 500;">{t.get("table", "-")}</td>
            <td style="padding: 10px 12px; color: #94a3b8;">{t.get("watermark_column", "-")}</td>
            <td style="padding: 10px 12px; color: #38bdf8; font-family: monospace;">{t.get("watermark_value", "-")}</td>
            <td style="padding: 10px 12px; color: #f1f5f9; text-align: right; font-weight: 600;">{t.get("delta_rows", 0):,}</td>
            <td style="padding: 10px 12px; color: {t_status_color}; font-weight: 600; text-align: center;">{t.get("status", "-")}</td>
        </tr>
        """

    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
      <meta charset="utf-8">
      <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background-color: #0b0f19; color: #f1f5f9; padding: 30px 15px; margin: 0; }}
        .card {{ max-width: 650px; margin: 0 auto; background: #161e2e; border: 1px solid #2d3748; border-radius: 12px; padding: 28px; box-shadow: 0 10px 25px rgba(0,0,0,0.5); }}
        .badge {{ display: inline-block; background: #3b82f6; color: #fff; font-weight: 700; font-size: 13px; padding: 4px 10px; border-radius: 6px; margin-bottom: 12px; }}
        h1 {{ font-size: 20px; margin: 8px 0 16px 0; color: #ffffff; }}
        .metrics-grid {{ display: flex; gap: 12px; margin: 20px 0; }}
        .metric-card {{ flex: 1; background: #1e293b; padding: 14px; border-radius: 8px; border: 1px solid #334155; text-align: center; }}
        .metric-label {{ font-size: 12px; color: #94a3b8; text-transform: uppercase; margin-bottom: 4px; }}
        .metric-val {{ font-size: 20px; font-weight: 700; color: #38bdf8; }}
        table {{ width: 100%; border-collapse: collapse; margin-top: 16px; font-size: 13px; }}
        th {{ background: #1e293b; color: #cbd5e1; text-align: left; padding: 10px 12px; border-bottom: 2px solid #475569; }}
        .footer {{ font-size: 12px; color: #64748b; margin-top: 24px; border-top: 1px solid #2d3748; padding-top: 16px; text-align: center; }}
      </style>
    </head>
    <body>
      <div class="card">
        <div class="badge">Incremental Refresh Digest</div>
        <h1>Project: {project_name}</h1>
        <p style="color: #94a3b8; font-size: 14px; margin: 0 0 16px 0;">Automated incremental sync completed on <strong>{executed_at}</strong></p>
        
        <table style="margin-bottom: 20px; width: 100%; background: #1e293b; border-radius: 8px; padding: 12px;">
            <tr>
                <td style="padding: 8px; color: #94a3b8;">Status:</td>
                <td style="padding: 8px;">{status_badge}</td>
                <td style="padding: 8px; color: #94a3b8;">Duration:</td>
                <td style="padding: 8px; color: #f1f5f9; font-weight: bold;">{duration_sec:.1f}s</td>
                <td style="padding: 8px; color: #94a3b8;">Total New Rows:</td>
                <td style="padding: 8px; color: #38bdf8; font-weight: bold;">{total_delta:,}</td>
            </tr>
        </table>

        <h3 style="font-size: 15px; color: #e2e8f0; margin-bottom: 8px;">Table Breakdown:</h3>
        <table>
            <thead>
                <tr>
                    <th>Table</th>
                    <th>Watermark Field</th>
                    <th>High-Watermark</th>
                    <th style="text-align: right;">New Rows</th>
                    <th style="text-align: center;">Status</th>
                </tr>
            </thead>
            <tbody>
                {table_rows_html}
            </tbody>
        </table>

        <div class="footer">
          &copy; 2026 Migration AI Studio &bull; Automated Incremental Engine &bull; Databricks Delta Lake
        </div>
      </div>
    </body>
    </html>
    """

    payload = {
        "sender": {"name": sender_name, "email": sender_email},
        "to": [{"email": to_email}],
        "subject": f"[{status}] Scheduled Migration Digest: {project_name} ({total_delta:,} new rows)",
        "htmlContent": html_content,
    }

    headers = {
        "accept": "application/json",
        "api-key": api_key,
        "content-type": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(BREVO_API_URL, json=payload, headers=headers)
            if resp.status_code in (200, 201, 202):
                print(f"[EMAIL SUCCESS] Digest email sent to {to_email}")
                return True, "Email sent successfully"
            else:
                print(f"[EMAIL ERROR] Brevo API status {resp.status_code}: {resp.text}")
                return False, resp.text
    except Exception as e:
        print(f"[EMAIL EXCEPTION] Failed to send digest to {to_email}: {e}")
        return False, str(e)
