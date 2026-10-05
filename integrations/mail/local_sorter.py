"""Free local ingestion. IMAP reads never move, delete or mark mail as read."""
import hashlib
import json
import mailbox
from email import message_from_bytes
from email.utils import parseaddr, parsedate_to_datetime
from pathlib import Path

from core.case_pipeline import process_parsed_email
from integrations.mail.contracts import MailSyncCursor
from integrations.mail.imap.adapter import GenericImapMailAdapter, message_body, _decode_header_value
from integrations.providers.enums import MailProvider


def sync_local_mail(db, *, token_dir, settings):
    adapter = GenericImapMailAdapter(token_dir=token_dir, settings=settings)
    key = 'local_imap_cursor_v1'
    try:
        saved = json.loads(db.get_meta(key) or '{}')
    except ValueError:
        saved = {}
    if not isinstance(saved, dict):
        saved = {}
    cursor = MailSyncCursor.from_dict(saved, provider=MailProvider.GENERIC_IMAP)
    result = adapter.sync(cursor=cursor)
    # Persist the cursor only after every message has been ingested; retries dedupe.
    for message in result.messages:
        payload = message.to_pipeline_payload()
        payload['received_at'] = message.internal_date
        process_parsed_email(db, payload, exclude_senders=settings.gmail_exclude_senders,
                             auto_status=False)
    cursor.cursor_token = result.new_cursor_token
    db.set_meta(key, json.dumps(cursor.to_dict()))
    return result


def import_mail_file(db, path: Path, *, exclude_senders=None):
    """EML/MBOX works offline for all providers, including Outlook exports."""
    if path.stat().st_size > 100 * 1024 * 1024:
        raise ValueError('Bitte Dateien bis 100 MB importieren.')
    if path.suffix.lower() == '.eml':
        messages = [message_from_bytes(path.read_bytes())]
        close = lambda: None
    elif path.suffix.lower() in {'.mbox', '.mbx'}:
        messages = mailbox.mbox(path, create=False)
        close = messages.close
    else:
        raise ValueError('Bitte eine EML- oder MBOX-Datei auswählen.')
    imported = duplicates = 0
    try:
        for message in messages:
            identifier = 'import:' + hashlib.sha256(message.as_bytes()).hexdigest()
            try:
                received = parsedate_to_datetime(message.get('Date', '')).isoformat()
            except (ValueError, TypeError, OverflowError):
                received = ''
            outcome = process_parsed_email(db, {
                'gmail_id': identifier, 'external_message_id': identifier,
                'provider': 'local_import', 'subject': _decode_header_value(message.get('Subject')),
                'sender': parseaddr(message.get('From', ''))[1], 'body_text': message_body(message),
                'received_at': received,
                'thread_id': message.get('In-Reply-To') or message.get('Message-ID') or '',
            }, exclude_senders=exclude_senders, auto_status=False)
            if outcome.get('skipped'):
                duplicates += 1
            else:
                imported += 1
    finally:
        close()
    return imported, duplicates
