"""Readable, explicitly synthetic passports with existing public-domain test portraits.

The older 'valid' fixture is an expired ICAO example with a drawn cartoon face.
These additive fixtures exercise real OCR and ArcFace without changing that regression data.
"""
import sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from app.services.mrz_service import compute_check_digit


def font(size):
    for name in ['C:/Windows/Fonts/consola.ttf', 'DejaVuSansMono.ttf']:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            pass
    raise RuntimeError('Install a monospace TrueType font for the demo generator')


def generate():
    samples = ROOT / 'backend/tests/demo_samples'
    output = ROOT / 'backend/audit_demo/final-fixtures'
    output.mkdir(parents=True, exist_ok=True)
    portrait = Image.open(samples / 'astronaut_public_domain.png').crop((150, 30, 310, 200)).resize((320, 340))
    for filename, name, surname, given, number, dob, expiry in [
        ('clean', 'JOHNATHAN DOE', 'DOE', 'JOHNATHAN', 'P1234567', '1985-04-12', '2030-04-12'),
        ('blacklist', 'VIKTOR KORZHOV', 'KORZHOV', 'VIKTOR', 'B7654321', '1978-11-20', '2027-11-20'),
        ('invalid', 'JOHNATHAN DOE', 'DOE', 'JOHNATHAN', 'P1234567', '1985-04-12', '2030-04-12'),
    ]:
        document = Image.new('RGB', (1600, 1000), '#eef2f5')
        draw = ImageDraw.Draw(document)
        draw.text((65, 25), 'SYNTHETIC DEMO - NOT A TRAVEL DOCUMENT', fill='#243345', font=font(28))
        draw.text((65, 85), 'PASSPORT / UTOPIA', fill='black', font=font(44))
        document.paste(portrait, (1190, 160))
        for i, text in enumerate([f'Name: {name}', f'Passport No: {number}', 'Nationality: UTO',
                                  f'Date of Birth: {dob}', 'Sex: M', f'Date of Expiry: {expiry}']):
            draw.text((65, 180 + i * 76), text, fill='black', font=font(34))
        first = f'P<UTO{surname}<<{given}'.ljust(44, '<')
        num = number.ljust(9, '<')
        birth = dob[2:].replace('-', '')
        exp = expiry[2:].replace('-', '')
        personal = '<' * 14
        second = num + compute_check_digit(num) + 'UTO' + birth + compute_check_digit(birth) + 'M' + exp + compute_check_digit(exp) + personal + compute_check_digit(personal)
        second += compute_check_digit(second[:10] + second[13:20] + second[21:43])
        if filename == 'invalid':
            second = second[:9] + str((int(second[9]) + 1) % 10) + second[10:]
        draw.rectangle((0, 735, 1600, 1000), fill='white')
        draw.text((65, 775), first, fill='black', font=font(48))
        draw.text((65, 855), second, fill='black', font=font(48))
        document.save(output / f'{filename}.png')
    print('Demo documents:', output)
    print('Matching selfie:', samples / 'astronaut_public_domain.png')
    print('Mismatched selfie:', samples / 'grace_hopper_public_domain.jpg')


if __name__ == '__main__':
    generate()
