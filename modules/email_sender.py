# modules/email_sender.py

import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from loguru import logger
import os

def send_email_with_multiple_attachments( # 함수명 변경
    sender_email: str,
    sender_password: str, # 또는 앱 비밀번호
    receiver_emails: list[str], # 단일 str 대신 list[str]로 변경
    smtp_server: str,
    smtp_port: int,
    subject: str,
    body: str,
    attachments: list[dict] = None, # 여러 첨부 파일을 위한 리스트 [{data: bytes, filename: str, mime_type: str}]
    report_format: str = "markdown" # 본문 형식 (plain 또는 html)
):
    """
    이메일을 통해 보고서와 특약 등 여러 파일을 전송합니다.

    Args:
        sender_email (str): 발신자 이메일 주소.
        sender_password (str): 발신자 이메일 비밀번호 또는 앱 비밀번호.
        receiver_emails (list[str]): 수신자 이메일 주소 목록.
        smtp_server (str): SMTP 서버 주소 (예: 'smtp.gmail.com').
        smtp_port (int): SMTP 포트 (예: 587).
        subject (str): 이메일 제목.
        body (str): 이메일 본문 내용.
        attachments (list[dict], optional): 첨부할 파일 목록. 각 딕셔너리는
                                            {"data": bytes, "filename": str, "mime_type": str} 형태.
                                            Defaults to None.
        report_format (str): 본문 형식. 'plain' 또는 'html' (마크다운은 'html'로 변환하여 사용).
    """
    try:
        msg = MIMEMultipart()
        msg['From'] = sender_email
        msg['To'] = ", ".join(receiver_emails) # 여러 수신자 처리
        msg['Subject'] = subject

        # 본문 추가 (마크다운을 HTML로 변환하여 이메일 본문으로 사용)
        if report_format == "markdown":
            html_body = f"""\
            <html>
              <body>
                <p>안녕하세요!</p>
                <p>요청하신 뉴스 트렌드 분석 보고서입니다.</p>
                <pre style="white-space: pre-wrap; font-family: monospace;">{body}</pre>
                <p>감사합니다.</p>
              </body>
            </html>
            """
            msg.attach(MIMEText(html_body, 'html'))
        else:
            msg.attach(MIMEText(body, 'plain'))

        # 여러 첨부 파일 추가
        if attachments:
            for attachment_info in attachments:
                data = attachment_info.get("data")
                filename = attachment_info.get("filename")
                mime_type = attachment_info.get("mime_type")

                if data and filename and mime_type:
                    maintype, subtype = mime_type.split('/', 1)
                    part = MIMEBase(maintype, subtype)
                    part.set_payload(data)
                    encoders.encode_base64(part)
                    part.add_header('Content-Disposition', f'attachment; filename= "{filename}"')
                    msg.attach(part)
                else:
                    logger.warning(f"유효하지 않은 첨부 파일 정보: {attachment_info}. 건너뜁니다.")

        server = smtplib.SMTP(smtp_server, smtp_port)
        server.starttls()  # TLS 보안 시작
        server.login(sender_email, sender_password)
        text = msg.as_string()
        server.sendmail(sender_email, receiver_emails, text) # receiver_emails는 리스트로 전달
        server.quit()
        logger.info(f"이메일이 {', '.join(receiver_emails)} (으)로 성공적으로 전송되었습니다.")
        return True
    except Exception as e:
        logger.error(f"이메일 전송 중 오류 발생: {e}")
        return False
