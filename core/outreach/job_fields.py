"""Evidence-based job fields. Pure functions: no network, workers or persistence."""
from dataclasses import dataclass
import re
from urllib.parse import urlsplit, parse_qs


ROLE = re.compile(r'\b(?:engineer|developer|architect|analyst|scientist|administrator|admin|consultant|specialist|manager|designer|tester|lead|director|DBA|SRE)\b', re.I)
LABEL = re.compile(r'^\s*(job\s*title|role\s*name|position\s*title|position|role|location|work\s*(?:mode|location)|duration|rate|experience|skills|job\s*description|responsibilities|requirements)\s*[:\-]\s*(.*)$', re.I)
TITLE_LABELS = {'job title', 'title', 'role name', 'position title', 'position', 'role'}
LOCATION_LABELS = {'location', 'work location'}


@dataclass(frozen=True)
class JobFields:
    title: str = ''
    location: str = ''
    title_evidence: str = ''
    location_evidence: str = ''
    review_reason: str = ''
    location_issue: str = ''


def compact(value):
    return re.sub(r'\s+', ' ', str(value or '')).strip()


def _label(line):
    if re.fullmatch(r'\s*(?:Role Overview|Location details)\s*', line, re.I):
        return None
    return (LABEL.match(line) or
            re.match(r'^\s*(title)\s*:\s*(.*)$', line, re.I) or
            re.match(r'^\s*(role|location)\s+([^:]+)$', line, re.I))


def _source_body(body):
    # Nvoids appends generated geography after its removal/help footer. It is
    # website metadata, not another explicit field supplied by the recruiter.
    return re.split(r'(?im)^\s*(?:To remove this job post send|Pages not loading,|Time Taken:)', str(body or ''), maxsplit=1)[0]


def _strip_noise(value):
    value = compact(value)
    value = re.sub(r'^.*?\bJob Openings? for\s+', '', value, flags=re.I)
    value = re.sub(r'\(\s*(?:locals? only|no\s*)\)', '', value, flags=re.I)
    value = re.sub(r'\s+(?:required|needed)\s+in\s+[A-Z]{2}\b.*$', '', value)
    # These are prefixes, never reasons to discard a whole role-bearing segment.
    prefix = r'^(?:(?:new\s+)?(?:urgent(?:ly)?|immediate|hot|new|actively)\s+)*(?:(?:job\s+)?(?:opening|opportunity|requirement|req|position|role|hiring|need|looking)\b[!:\s-]*(?:for\s+|of\s+)?|locals?\s+only\s*[:\-]\s*|only\s+locals?\s*[:\-]\s*|FTE\s*[-:]\s*|(?:hybrid|remote|onsite)\s*[-:]\s*)'
    for _ in range(12):
        cleaned = re.sub(prefix, '', value, count=1, flags=re.I).strip()
        if cleaned == value:
            break
        value = cleaned
    value = re.sub(r'\b\d+\+?\s*(?:years?|yrs?)\s*(?:of\s+)?(?:experience|exp)?\b', '', value, flags=re.I)
    value = re.sub(r'\([^)]*(?:onsite|hybrid|remote|openings|years|interview)[^)]*\)', '', value, flags=re.I)
    value = re.sub(r'\s+(?:local\s+to|only\s+locals|onsite\s+job\s+role|face\s+to\s+face|F2F\s+interview)\b.*$', '', value, flags=re.I)
    value = re.sub(r'\s+(?:in\s+)?[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*,\s*[A-Z]{2}\b.*$', '', value)
    value = re.sub(r'\s+(?:in\s+)?(?:100%\s*)?(?:remote|hybrid|onsite|on-site)(?:\s+only)?\s*$', '', value, flags=re.I)
    value = re.sub(r'\s+(?:required|needed|ASAP)\s*$', '', value, flags=re.I)
    value = re.sub(r',\s*[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\s+[A-Z]{2}\s*$', '', value)
    value = re.sub(r'\(\s*\)', '', value)
    return compact(value).strip(' ,:;@-/|')


def clean_title(headline):
    """Return a complete role, or blank. Never truncate stored titles."""
    value = compact(headline)
    value = re.sub(r'\s+at\s+[^\n]+,\s*USA\s*$', '', value, flags=re.I)
    if not value or value.endswith(('...', '…')):
        return ''  # A truncated headline is not enough evidence to reconstruct it.
    parts = re.split(r'\s*\|+\s*|\s*//+\s*|\s*::+\s*|\s+[-–—]\s+|:\s+', value)
    candidates = []
    for index, part in enumerate(parts):
        candidate = _strip_noise(part)
        if ROLE.search(candidate) and not re.search(r'@|https?://|\$|\b(?:interview|resume|visa|only locals)\b', candidate, re.I):
            # Retain a meaningful specialization before a role separator.
            if index and re.fullmatch(r'(?:AI|Agentic AI|Gen(?:erative)? AI|Full\s*stack Python)', parts[index - 1], re.I):
                candidate = compact(parts[index - 1]) + ' - ' + candidate
            # Whitelist technical qualifiers, not arbitrary recruiting prose.
            if index + 1 < len(parts):
                qualifier = _strip_noise(parts[index + 1])
                if not ROLE.search(qualifier) and re.fullmatch(r'[\w\s()/+&.,-]+', qualifier) and re.search(r'\b(?:MDM|Profisee|Alteryx|AWS Glue|Azure Cloud|Machine Learning|MLOps|GenAI)\b', qualifier, re.I) and not re.search(r'\b(?:contract|years|only|interview|location)\b|\$', qualifier, re.I):
                    candidate += ' - ' + qualifier
            if candidate.casefold() not in [x.casefold() for x in candidates]:
                candidates.append(candidate)
    if len(candidates) == 1:
        return candidates[0]
    if len(candidates) == 2 and re.match(r'^Architect\b', candidates[1], re.I):
        return candidates[0] + ' / ' + candidates[1]
    return ''  # Multiple independent roles require review, not first-role guessing.


def _fields(body):
    lines = _source_body(body).splitlines()
    found = []
    for index, line in enumerate(lines):
        match = _label(line)
        if not match:
            continue
        label = compact(match[1]).lower()
        if label not in TITLE_LABELS | LOCATION_LABELS:
            continue
        value = match[2].strip()
        # Include wrapped continuation, or a value on the next nonblank line.
        for extra in lines[index + 1:index + 5]:
            if _label(extra) or re.match(r'^\s*[A-Za-z][A-Za-z /]{1,35}:', extra) or re.match(r'^\s*(?:https?://|From:|Reply to:|Email:|Job Summary|Key Requirements)', extra, re.I):
                break
            if not extra.strip():
                if value:
                    break
                continue
            if value and (len(value) > 160 or len(extra.split()) > 18):
                break
            if value and value.count('(') <= value.count(')') and not re.search(r'(?:[&/,+-]|\b(?:with|and))\s*$', value, re.I):
                wrapped_city = label in LOCATION_LABELS and ',' not in value and re.match(r'^\s*[A-Z][a-z]+,\s*[A-Z]{2}\b', extra)
                wrapped_role = label in TITLE_LABELS and not ROLE.search(value) and ROLE.search(extra) and len(extra.split()) <= 5
                if not wrapped_city and not wrapped_role and not re.match(r'^\s*(?:[&/,+]|and\b|or\b|\(?\s*(?:hybrid|onsite|remote)\b)', extra, re.I):
                    break
            value = compact(value + ' ' + extra)
        if value:
            found.append((label, value))
    return found


def clean_location(value):
    value = compact(value).strip(' ,;:-')
    value = re.split(r'\s*[-–]\s*(?:who|need|only|interview)\b', value, flags=re.I)[0]
    value = re.sub(r'\s*,\s*', ', ', value)
    if not value or len(value) > 220 or re.search(r'@|https?://|\$|\b(?:duration|experience|salary|email)\b', value, re.I):
        return ''
    if re.fullmatch(r'(?:100%\s*)?remote(?:\s*,\s*remote)*(?:\s*,\s*USA)?', value, re.I):
        return 'Remote'
    # Keep work arrangement, not interview/relocation instructions or schedules.
    mode = re.search(r'\b(hybrid|onsite|on-site|remote)\b', value, re.I)
    if mode:
        if mode.start() == 0 and re.fullmatch(r'\s*-\s*[A-Z][a-z]+,\s*[A-Z]{2}', value[mode.end():]):
            return value[mode.end():].strip(' -') + ' (' + mode[1].replace('-', '').title() + ')'
        if re.search(r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*,\s*[A-Z]{2}\b', value[mode.end():]):
            return value  # A later named location must not be discarded.
        place = value[:mode.start()].rstrip(' (-,')
        place = re.sub(r'\s*\(?\s*(?:\d+\s*days?|day\s*\d+)\s*$', '', place, flags=re.I).rstrip(' (-,')
        place = re.sub(r'\(?\s*100%\s*$', '', place).rstrip(' (-,')
        work_mode = mode[1].replace('-', '').title()
        if place:
            restriction = re.search(r'\bfor\s+([A-Z]{2,4}\s+(?:zone|time\s*zone))', value[mode.end():], re.I)
            suffix = ' for ' + restriction[1] if restriction else ''
            return place + ' (' + work_mode + suffix + ')'
        return value  # Preserve geographic restrictions such as "Remote (US only)".
    value = re.split(r'\s*[-–]\s*(?:need|only|interview)|\b(?:need only|interview mandatory)\b', value, flags=re.I)[0]
    return re.sub(r',\s*USA$', '', value, flags=re.I)


def resolve_job_fields(headline, description='', location='', ai_candidate=None):
    """Explicit JD labels outrank website headings; location uncertainty omits it."""
    fields = _fields(description)
    titles = [(clean_title(v), v) for k, v in fields if k in TITLE_LABELS]
    titles = [(t, evidence) for t, evidence in titles if t]
    unique = {t.casefold() for t, _ in titles}
    if len(unique) > 1:
        return JobFields(review_reason='Conflicting explicit job titles; review the source listing')
    evidence = ''
    title = ''
    if titles:
        title, evidence = titles[0]
    else:
        # Saved descriptions may contain the intact website heading, even when
        # their stored title has already been damaged by an older cleaner.
        source_header = next((compact(line) for line in str(description).splitlines()[:8]
                              if re.search(r'\s+at\s+.+,\s*USA\s*$', line, re.I)), '')
        evidence = source_header or compact(headline)
        title = clean_title(evidence)
        if not title:
            alternatives = [clean_title(p) for p in re.split(r'\|+|//+|\s+[-–—]\s+', evidence)]
            if len({t.casefold() for t in alternatives if t}) > 1:
                return JobFields(title_evidence=evidence, review_reason='Multiple roles in headline; review the source listing')
    location_pairs = [(clean_location(v), v) for k, v in fields if k in LOCATION_LABELS]
    locations = list(dict.fromkeys(v for v, _ in location_pairs if v))
    location_evidence = next((raw for clean, raw in location_pairs if clean == locations[0]), '') if len(locations) == 1 else ''
    resolved_location = locations[0] if len(locations) == 1 else ''
    location_issue = 'Conflicting explicit locations; omitted from subject' if len(locations) > 1 else ''
    if not locations:
        # Extract inline city/state or work mode from the *original* headline,
        # excluding the website's frequently incorrect "at ..., USA" suffix.
        raw_header = next((compact(line) for line in str(description).splitlines()[:8]
                           if re.search(r'\s+at\s+.+,\s*USA\s*$', line, re.I)), '')
        raw = re.sub(r'\s+at\s+.+,\s*USA\s*$', '', raw_header or compact(headline), flags=re.I)
        city = re.findall(r'\b[A-Z][a-zA-Z.]+(?:\s+[A-Z][a-zA-Z.]+)*,\s*[A-Z]{2}\b', raw)
        if not city:
            city = re.findall(r',\s*([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\s+[A-Z]{2})\b', raw)
        if city:
            resolved_location = ' / '.join(dict.fromkeys(city))
        elif re.search(r'\bremote\b', raw, re.I):
            resolved_location = 'Remote'
        elif 'USA' not in str(description) and not str(description).lstrip().startswith('Home'):
            resolved_location = clean_location(location)
        location_evidence = resolved_location
    if not resolved_location and not location_issue:
        location_issue = 'No reliable location; omitted from subject'
    if not title and isinstance(ai_candidate, dict):
        suggestion = ai_candidate.get('job_title')
        if isinstance(suggestion, str):
            candidate = clean_title(suggestion)
            # Selection from source wording, not invented role reconstruction.
            haystack = compact(str(headline) + ' ' + str(description)).casefold()
            if candidate and candidate.casefold() in haystack:
                title, evidence = candidate, suggestion
    return JobFields(title, resolved_location, evidence, location_evidence,
                     '' if title else 'No unambiguous professional job title; review the source listing', location_issue)


def render_subject(template, fields, values):
    if fields.review_reason or not fields.title:
        raise ValueError(fields.review_reason or 'Missing job title')
    if not isinstance(template, str) or '\n' in template or '\r' in template:
        raise ValueError('Subject template must be a single line')
    subject = template
    for key, value in dict(values, job_title=fields.title, location=fields.location).items():
        subject = subject.replace('{' + key + '}', str(value or ''))
    if re.search(r'[{}\r\n]', subject):
        raise ValueError('Subject has unresolved placeholders or line breaks')
    subject = re.sub(r'\(\s*\)', '', subject)
    subject = re.sub(r'\s+[-–—]\s*(?=[-–—](?:\s|$))', ' ', subject)
    subject = subject.strip().strip('-–— ').strip()
    if not subject:
        raise ValueError('Subject is empty')
    return compact(subject)


def listing_identity(url):
    """Stable same-listing comparison; do not change stored dedup hashes."""
    parsed = urlsplit(str(url or ''))
    if parsed.hostname == 'jobs.nvoids.com':
        key = parse_qs(parsed.query).get('id', [''])[0]
        if key.isdigit():
            return 'nvoids:' + key
    return str(url or '').strip().rstrip('/').lower()
