import io
from pathlib import Path
import sys

backend_dir = Path(__file__).resolve().parent / "backend"
sys.path.insert(0, str(backend_dir))

from PIL import Image, ImageDraw
from fastapi.testclient import TestClient
from app.main import app

img = Image.new("RGB", (1600, 1000), "white")
draw = ImageDraw.Draw(img)
draw.text((80, 80), "PASSPORT", fill="black")
draw.text((80, 150), "Name: ANNA MARIA ERIKSSON", fill="black")
draw.text((80, 210), "Passport No: L898902C", fill="black")
draw.text((80, 270), "Nationality: UTO", fill="black")
draw.text((80, 330), "Date of Birth: 1969-08-06", fill="black")
draw.text((80, 390), "Date of Expiry: 1994-06-23", fill="black")
draw.text((80, 780), "P<UTOERIKSSON<<ANNA<MARIA<<<<<<<<<<<<<<<<<<<", fill="black")
draw.text((80, 840), "L898902C<3UTO6908061F9406236ZE184226B<<<<<14", fill="black")

buf = io.BytesIO()
img.save(buf, format="PNG")
payload = buf.getvalue()

with TestClient(app) as client:
    assert client.get("/health").status_code == 200
    response = client.post(
        "/api/screen",
        files={"file": ("demo.png", payload, "image/png")},
        data={"document_type": "passport"},
    )
    print("SCREEN_STATUS", response.status_code)
    if response.status_code != 200:
        print(response.text)
        raise SystemExit(1)
    body = response.json()
    print("CASE", body["case_id"], "RISK", body["risk"]["risk_level"], body["risk"]["risk_score"])
    assert body["case_id"].startswith("CASE-")
    assert client.get("/api/cases").status_code == 200
    assert client.get("/api/documents/B7654321/status").json()["blacklisted"] is True

    # Test officer decision
    decision_resp = client.post(
        f"/api/cases/{body['case_id']}/decision",
        json={"decision": "APPROVE", "notes": "Verified at immigration counter", "officer_id": "OFFICER-001"},
    )
    assert decision_resp.status_code == 200
    assert decision_resp.json()["case"]["officer_decision"]["decision"] == "APPROVE"

print("E2E_OK")

