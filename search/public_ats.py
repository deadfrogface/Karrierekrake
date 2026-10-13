"""Read official public job feeds for discovered Greenhouse/Lever/Ashby boards."""
from __future__ import annotations

import html
import json
import re
from datetime import datetime, timezone
from urllib.parse import parse_qs, urlsplit

from core.geo_normalize import source_location_blob_to_fields
from search.jsonld import job_from_job_posting


def board_endpoint(url: str):
    parts = urlsplit(url)
    host = (parts.hostname or '').lower()
    segments = [x for x in parts.path.split('/') if x]
    if not segments:
        return None
    board = segments[0]
    if host in {'boards.greenhouse.io', 'job-boards.greenhouse.io'}:
        if board == 'embed':
            board = parse_qs(parts.query).get('for', [''])[0]
        provider, base = 'greenhouse', 'https://boards-api.greenhouse.io/v1/boards/'
        suffix = '/jobs?content=true'
    elif host in {'jobs.lever.co', 'jobs.eu.lever.co'}:
        provider = 'lever'
        base = 'https://api.eu.lever.co/v0/postings/' if '.eu.' in host else 'https://api.lever.co/v0/postings/'
        suffix = '?mode=json'
    elif host == 'jobs.ashbyhq.com':
        provider, base = 'ashby', 'https://api.ashbyhq.com/posting-api/job-board/'
        suffix = '?includeCompensation=true'
    else:
        return None
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,100}', board):
        return None
    return provider, board, base + board + suffix


def read_board(url: str, pages):
    endpoint = board_endpoint(url)
    if endpoint is None:
        return None
    provider, board, api = endpoint
    text, _ = pages.get(api)
    data = json.loads(text)
    rows = data if provider == 'lever' else data.get('jobs') if isinstance(data, dict) else None
    if not isinstance(rows, list):
        raise ValueError('invalid_public_job_feed')
    jobs = []
    for row in rows:
        if not isinstance(row, dict) or row.get('isListed') is False:
            continue
        if provider == 'greenhouse':
            title, target = row.get('title'), row.get('absolute_url')
            description = html.unescape(str(row.get('content') or ''))
            location = (row.get('location') or {}).get('name', '')
            apply_url = target
            published = row.get('first_published', '')
            address = {}
        elif provider == 'lever':
            title, target = row.get('text'), row.get('hostedUrl')
            description = str(row.get('description') or row.get('descriptionPlain') or '')
            for section in row.get('lists') or []:
                if isinstance(section, dict):
                    description += '\n' + str(section.get('content') or '')
            description += '\n' + str(row.get('additional') or '')
            location = (row.get('categories') or {}).get('location', '')
            apply_url = row.get('applyUrl') or target
            published = ''
            if isinstance(row.get('createdAt'), (int, float)):
                published = datetime.fromtimestamp(row['createdAt'] / 1000, timezone.utc).isoformat()
            address = {}
        else:
            title, target = row.get('title'), row.get('jobUrl')
            description = row.get('descriptionHtml') or row.get('descriptionPlain') or ''
            location = row.get('location') or ''
            address = (row.get('address') or {}).get('postalAddress') or {}
            apply_url = row.get('applyUrl') or target
            published = row.get('publishedAt') or ''
        if not title or not target or urlsplit(str(target)).scheme not in {'http', 'https'}:
            continue
        fields = source_location_blob_to_fields(str(location))
        address = {**{'addressLocality': fields.get('city') or location,
                      'addressCountry': fields.get('country_code') or ''}, **address}
        item = {'title': title, 'url': target, 'description': description,
                # Board namespace is verified by the public ATS URL; don't invent a legal company name.
                'hiringOrganization': {'name': row.get('company_name') or board},
                'jobLocation': {'address': address}, 'datePosted': published}
        if row.get('isRemote') or str(row.get('workplaceType') or '').lower() == 'remote':
            item['jobLocationType'] = 'TELECOMMUTE'
        job = job_from_job_posting(item, source='company_sites')
        if job:
            if apply_url and urlsplit(str(apply_url)).scheme in {'http', 'https'}:
                job.application_url = str(apply_url)
            jobs.append(job)
    return jobs
