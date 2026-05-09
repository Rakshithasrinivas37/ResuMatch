import smtplib
import json
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from crewai.tools import tool
import os


@tool("email_sender_tool")
def EmailSenderTool(input_data: str) -> str:
    """Sends job match results email to candidate with CSV attached.
    Input: JSON string with mail_id, app_password, candidate_name,
    subject, body and csv_path."""

    try:
        data           = json.loads(input_data)
        mail_id        = data.get("mail_id")
        app_password   = data.get("app_password")
        candidate_name = data.get("candidate_name")
        subject        = data.get("subject")
        body           = data.get("body")
        csv_path       = data.get("csv_path", "match_results.csv")

        if not all([mail_id, app_password, subject, body]):
            return "Error: mail_id, app_password, subject and body are required."

        if not os.path.exists(csv_path):
            return f"Error: CSV file not found at {csv_path}"

        # ── Build email ────────────────────────────────
        msg            = MIMEMultipart("mixed")
        msg["Subject"] = subject
        msg["From"]    = mail_id
        msg["To"]      = mail_id   # ✅ send to candidate (same as sender for now)

        # ── Plain text body ────────────────────────────
        msg.attach(MIMEText(body, "plain"))

        # ── HTML body ──────────────────────────────────
        html_body = f"""
        <html>
        <body style="font-family: Arial, sans-serif; max-width: 600px;">
            <div style="background:#f8f9fa; padding:20px; border-radius:8px;">
                <h2 style="color:#2c3e50;">🎯 ResuMatch Results</h2>
                <div style="white-space: pre-line; color:#34495e;">
                    {body}
                </div>
                <div style="margin-top:20px; padding:15px;
                     background:#e8f4fd; border-radius:6px;">
                    <p style="margin:0; color:#2980b9;">
                        📎 Your complete job match report is attached
                        as a CSV file. Open it to see full details
                        including skill gap analysis, upskilling
                        roadmap and all interview tips.
                    </p>
                </div>
            </div>
        </body>
        </html>
        """
        msg.attach(MIMEText(html_body, "html"))

        # ── Attach CSV file ────────────────────────────
        with open(csv_path, "rb") as f:
            attachment = MIMEBase("application", "octet-stream")
            attachment.set_payload(f.read())
            encoders.encode_base64(attachment)
            attachment.add_header(
                "Content-Disposition",
                f"attachment; filename={os.path.basename(csv_path)}"
            )
            msg.attach(attachment)

        # ── Send via Gmail SMTP ────────────────────────
        server = smtplib.SMTP("smtp.gmail.com", 587)
        server.starttls()
        server.login(mail_id, app_password)
        server.sendmail(mail_id, mail_id, msg.as_string())
        server.quit()

        print(f"✅ Email sent to {mail_id} with {csv_path} attached")

        return json.dumps({
            "status" : "success",
            "sent_to": mail_id,
            "subject": subject,
            "csv"    : csv_path
        })

    except smtplib.SMTPAuthenticationError:
        return ("Error: Gmail authentication failed. "
                "Check your app password at "
                "myaccount.google.com/apppasswords")
    except Exception as e:
        return f"Error sending email: {str(e)}"