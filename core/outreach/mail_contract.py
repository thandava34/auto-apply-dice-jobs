"""Shared, provider-independent message safety. No account or network access."""
import re
from email.utils import getaddresses


def address_list(value):
    text = str(value or "").strip()
    if not text:
        return []
    if "\r" in text or "\n" in text:
        raise ValueError("Recipient fields cannot contain line breaks")
    # The UI accepts bare addresses separated by commas or semicolons.
    result = []
    for token in re.split(r"[,;]", text):
        token = token.strip()
        if not re.fullmatch(r"[^\s@,;<>]+@[^\s@,;<>]+\.[^\s@,;<>]+", token):
            raise ValueError("Invalid email address in recipient list")
        if token.casefold() not in {x.casefold() for x in result}:
            result.append(token)
    return result


def normalized_text(value):
    return str(value or "").replace("\r\n", "\n").replace("\r", "\n").strip()


def verify_mime(message, job, subject, body, attachment_name="", attachment_bytes=None):
    """Compare a retrieved MIME message to the intended content, including bytes."""
    for header, key in (("To", "Recruiter Email"), ("Cc", "CC"), ("Bcc", "BCC")):
        actual = {addr.casefold() for _, addr in getaddresses(message.get_all(header, []))}
        expected = {addr.casefold() for addr in address_list(job.get(key, ""))}
        if actual != expected:
            raise ValueError(f"Saved {header} recipients do not match the intended message")
    if str(message.get("Subject", "")) != subject:
        raise ValueError("Saved subject does not match")
    plain = message.get_body(preferencelist=("plain",))
    if plain is None or normalized_text(plain.get_content()) != normalized_text(body):
        raise ValueError("Saved message body does not match")
    attachments = list(message.iter_attachments())
    if len(attachments) != (1 if attachment_name else 0):
        raise ValueError("Saved attachment count does not match")
    if attachment_name:
        part = attachments[0]
        if part.get_filename() != attachment_name or part.get_payload(decode=True) != attachment_bytes:
            raise ValueError("Saved attachment filename or bytes do not match")
