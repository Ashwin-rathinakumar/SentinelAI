from pathlib import Path
import sys

backend_dir = Path(__file__).resolve().parent / "backend"
sys.path.insert(0, str(backend_dir))

from app.main import app
from app.services.mrz_service import extract_mrz
from app.services.screening_services import database_lookup

paths = app.openapi().get("paths", {})
assert "/api/screen" in paths
assert "/api/cases" in paths
assert "/api/cases/{case_id}/decision" in paths

mrz = extract_mrz("P<UTOERIKSSON<<ANNA<MARIA<<<<<<<<<<<<<<<<<<<\nL898902C<3UTO6908061F9406236ZE184226B<<<<<14", [])
assert mrz["mrz_detected"] and mrz["mrz_valid"]
assert database_lookup("B7654321").blacklisted is True

print("BACKEND_SMOKE_OK", sorted(paths.keys()))

