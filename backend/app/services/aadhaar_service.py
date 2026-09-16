"""Aadhaar visual extraction; no claim of UIDAI or citizenship verification."""
import re
from datetime import date, datetime
import cv2
from app.services.document_type_service import IDENTIFIER

DOB_LABEL_RE = re.compile(
    r"(?:date\s*of\s*birth|d\s*[o0]\s*b|year\s*of\s*birth|y\s*[o0]\s*b|जन्म(?:तिथि)?|जन्म\s*वर्ष)",
    re.I,
)
YOB_LABEL_RE = re.compile(r"(?:year\s*of\s*birth|y\s*[o0]\s*b|जन्म\s*वर्ष)", re.I)
DATE_RE = re.compile(r"(?<!\d)(\d{1,2})\s*([/-])\s*(\d{1,2})\s*\2\s*(\d{4})(?!\d)")
GENDER_RE = re.compile(r"(?<![A-Za-z])(FEMALE|MALE|TRANSGENDER)(?![A-Za-z])", re.I)
NAME_EXCLUSIONS_RE = re.compile(
    r"government|india|aadhaa?r|identification|proof|identity|citizenship|verification|"
    r"authenticat|birth|address|gender|male|female|transgender|unique|issued?|date|qr\s*code|offline\s*xml|"
    r"should|scanning|download|enrolment|enrollment",
    re.I,
)


def mask_numbers(value):
    """Redact identifiers recursively, including OCR text, regions and DB records."""
    if isinstance(value, str):
        return IDENTIFIER.sub(lambda m: 'XXXX XXXX ' + re.sub(r'\s', '', m[0])[-4:], value)
    if isinstance(value, dict):
        return {k: mask_numbers(v) for k, v in value.items()}
    if isinstance(value, list):
        return [mask_numbers(v) for v in value]
    return value


def extract_aadhaar(text: str, regions: list) -> dict:
    from app.services.field_extractor import _group_lines
    raw_lines = [s.strip() for s in text.splitlines() if s.strip()]
    grouped_lines = _group_lines([r for r in regions if isinstance(r, dict) and r.get('box')])
    # Keep both sources: grouping helps split OCR fragments, while raw order is a
    # reliable fallback when a tall/rotated region causes unrelated rows to merge.
    lines = list(dict.fromkeys([s.strip() for s in grouped_lines + raw_lines if s.strip()]))
    fields = {}

    def put(key, raw, normalized=None, required=False):
        fields[key] = {'raw': raw, 'normalized': normalized or raw,
                       'status': 'DETECTED' if raw else 'REQUIRED_MISSING' if required else 'OPTIONAL_MISSING'}

    def normalize_name_candidate(value: str) -> str:
        value = re.sub(r"\s+", " ", value).strip(" .,:;/-")
        return re.sub(r"(?<=[a-z])(?=[A-Z])", " ", value)

    def plausible(value: str, *, explicitly_labeled: bool = False) -> bool:
        candidate = normalize_name_candidate(value)
        if not candidate or len(candidate) > 60 or NAME_EXCLUSIONS_RE.search(candidate):
            return False
        if not re.fullmatch(r"[A-Za-z][A-Za-z .'-]*", candidate):
            return False
        words = re.findall(r"[A-Za-z]+(?:['-][A-Za-z]+)?", candidate)
        if len(words) > 5 or any(len(word) == 1 for word in words):
            return False
        # Unlabelled single tokens are too ambiguous unless OCR visibly merged a
        # mixed-case multiword name such as ManisSingh.
        return explicitly_labeled or len(words) >= 2

    def box_metrics(region: dict) -> tuple[float, float, float, float] | None:
        box = region.get('box') or []
        if len(box) < 4:
            return None
        xs = [float(point[0]) for point in box]
        ys = [float(point[1]) for point in box]
        return min(xs), min(ys), max(xs), max(ys)

    name = None
    # Explicit labels are useful when present, but are not required on Aadhaar.
    for i, line in enumerate(lines):
        label = re.search(r'(?:\bname\b|नाम)\s*[:/]\s*(.*)', line, re.I)
        candidate = label[1].strip() if label else ''
        if label and not candidate and i + 1 < len(lines):
            candidate = lines[i + 1]
        if plausible(candidate, explicitly_labeled=True):
            name = normalize_name_candidate(candidate)
            break

    # Prefer the closest horizontally aligned English OCR region above DOB/YOB.
    boxed_dob_found = False
    if not name:
        boxed = [(region, box_metrics(region)) for region in regions if isinstance(region, dict)]
        boxed = [(region, box) for region, box in boxed if box is not None]
        candidates: list[tuple[float, str]] = []
        for dob_region, dob_box in boxed:
            if not DOB_LABEL_RE.search(str(dob_region.get('text', ''))):
                continue
            boxed_dob_found = True
            dx1, dy1, dx2, _dy2 = dob_box
            dob_height = max(_dy2 - dy1, 1.0)
            for region, candidate_box in boxed:
                candidate = str(region.get('text', '')).strip()
                cx1, _cy1, cx2, cy2 = candidate_box
                vertical_gap = dy1 - cy2
                horizontal_overlap = max(0.0, min(dx2, cx2) - max(dx1, cx1))
                left_alignment = abs(cx1 - dx1)
                if (
                    0 <= vertical_gap <= max(120.0, dob_height * 3)
                    and (horizontal_overlap > 0 or left_alignment <= 120.0)
                    and plausible(candidate)
                ):
                    candidates.append((vertical_gap + left_alignment * 0.1, normalize_name_candidate(candidate)))
        if candidates:
            name = min(candidates, key=lambda item: item[0])[1]

    # Preserve a sequence fallback for engines that return text without boxes.
    if not name and not boxed_dob_found:
        for i, line in enumerate(lines):
            if DOB_LABEL_RE.search(line):
                nearby_names = [
                    normalize_name_candidate(prior)
                    for prior in reversed(lines[max(0, i - 3):i])
                    if plausible(prior)
                ]
                if nearby_names:
                    name = nearby_names[0]
                    break
    put('full_name', name, required=True)

    dob = yob = None
    for i, line in enumerate(lines):
        if not DOB_LABEL_RE.search(line):
            continue
        nearby = line + ' ' + (lines[i+1] if i+1 < len(lines) else '')
        match = DATE_RE.search(nearby)
        if match:
            try:
                raw_date = f"{match[1]}{match[2]}{match[3]}{match[2]}{match[4]}"
                parsed = datetime.strptime(raw_date.replace('-', '/'), '%d/%m/%Y').date()
                if date(1900, 1, 1) <= parsed <= date.today():
                    dob = (raw_date, parsed.isoformat())
            except ValueError:
                pass
        elif YOB_LABEL_RE.search(line):
            match = re.search(r'\b(19\d{2}|20\d{2})\b', nearby)
            if match and int(match[1]) <= date.today().year:
                yob = match[1]
    put('date_of_birth', dob[0] if dob else None, dob[1] if dob else None)
    put('year_of_birth', yob)
    gender = GENDER_RE.search(text)
    put('gender', gender[1].upper() if gender else None)
    numbers = {re.sub(r'\s', '', m[0]) for m in IDENTIFIER.finditer(text)}
    number = next(iter(numbers)) if len(numbers) == 1 else None
    put('id_number', number, required=True)
    put('masked_document_number', 'XXXX XXXX ' + number[-4:] if number else None)
    put('issuing_country', 'India')
    return fields


def detect_qr(image) -> dict:
    try:
        found, points = cv2.QRCodeDetector().detect(image)
        return {'status': 'QR_DETECTED_NOT_VERIFIED' if found and points is not None else 'QR_NOT_FOUND',
                'cryptographically_verified': False}
    except cv2.error:
        return {'status': 'QR_DETECTION_UNAVAILABLE', 'cryptographically_verified': False}
