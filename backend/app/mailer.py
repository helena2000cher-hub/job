"""Outgoing mail: email confirmation and password reset links.

With SMTP settings in .env letters go through the mail server (e.g. Yandex Mail with an app
password); without them the letter is written to the server log — enough for a local run.
"""

import logging
import smtplib
from email.message import EmailMessage
from typing import Protocol

log = logging.getLogger(__name__)


class Mailer(Protocol):
    def send(self, to: str, subject: str, text: str) -> None: ...


class LogMailer:
    def send(self, to: str, subject: str, text: str) -> None:
        log.warning("Письмо не отправлено (SMTP не настроен). Кому: %s\n%s\n%s", to, subject, text)


class SmtpMailer:
    def __init__(self, host: str, port: int, user: str, password: str, sender: str) -> None:
        self.host, self.port = host, port
        self.user, self.password = user, password
        self.sender = sender or user

    def send(self, to: str, subject: str, text: str) -> None:
        message = EmailMessage()
        message["From"] = self.sender
        message["To"] = to
        message["Subject"] = subject
        message.set_content(text)
        with smtplib.SMTP_SSL(self.host, self.port, timeout=20) as smtp:
            smtp.login(self.user, self.password)
            smtp.send_message(message)
