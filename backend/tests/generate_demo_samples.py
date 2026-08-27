from __future__ import annotations

from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw, ImageFilter
import cv2

OUTPUT_DIR = Path(__file__).resolve().parent / 'demo_samples'
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def create_synthetic_face(seed: int = 1, gender: str = 'F') -> np.ndarray:
    img = np.full((300, 240, 3), 240, dtype=np.uint8)
    skin_color = (195, 220, 245) if seed % 2 == 0 else (180, 205, 235)
    cv2.ellipse(img, (120, 150), (70, 95), 0, 0, 360, skin_color, -1)
    cv2.ellipse(img, (120, 150), (70, 95), 0, 0, 360, (140, 160, 180), 2)
    eye_y = 135
    cv2.ellipse(img, (90, eye_y), (14, 8), 0, 0, 360, (255, 255, 255), -1)
    cv2.circle(img, (90, eye_y), 5, (80, 50, 30), -1)
    cv2.ellipse(img, (150, eye_y), (14, 8), 0, 0, 360, (255, 255, 255), -1)
    cv2.circle(img, (150, eye_y), 5, (80, 50, 30), -1)
    cv2.line(img, (75, eye_y - 14), (105, eye_y - 12), (50, 35, 25), 3)
    cv2.line(img, (135, eye_y - 12), (165, eye_y - 14), (50, 35, 25), 3)
    cv2.line(img, (120, 140), (116, 170), (160, 175, 195), 2)
    cv2.line(img, (116, 170), (124, 170), (160, 175, 195), 2)
    cv2.ellipse(img, (120, 195), (22, 7), 0, 0, 360, (120, 130, 200), -1)
    hair_color = (30, 25, 20) if seed % 3 == 0 else (60, 45, 30)
    if gender == 'F':
        cv2.ellipse(img, (120, 105), (76, 50), 0, 180, 360, hair_color, -1)
        cv2.rectangle(img, (44, 105), (60, 200), hair_color, -1)
        cv2.rectangle(img, (180, 105), (196, 200), hair_color, -1)
    else:
        cv2.ellipse(img, (120, 100), (74, 45), 0, 180, 360, hair_color, -1)
    return img


def draw_passport_page(
    country: str = 'UTOPIA',
    name: str = 'ANNA MARIA ERIKSSON',
    doc_number: str = 'L898902C',
    nationality: str = 'UTO',
    dob: str = '1969-08-06',
    gender: str = 'F',
    expiry: str = '1994-06-23',
    mrz_line1: str = 'P<UTOERIKSSON<<ANNA<MARIA<<<<<<<<<<<<<<<<<<<',
    mrz_line2: str = 'L898902C<3UTO6908061F9406236ZE184226B<<<<<14',
    face_seed: int = 1,
    blur: bool = False,
) -> Image.Image:
    width, height = 1600, 1000
    img = Image.new('RGB', (width, height), (250, 250, 250))
    draw = ImageDraw.Draw(img)

    draw.rectangle([0, 0, width, 110], fill=(224, 231, 255))
    draw.rectangle([0, 110, width, 114], fill=(59, 130, 246))

    draw.text((80, 35), f'{country} PASSPORT', fill=(30, 58, 138))
    draw.text((80, 75), 'OFFICIAL TRAVEL DOCUMENT', fill=(71, 85, 105))

    face_arr = create_synthetic_face(seed=face_seed, gender=gender)
    face_pil = Image.fromarray(cv2.cvtColor(face_arr, cv2.COLOR_BGR2RGB))
    face_resized = face_pil.resize((240, 300), Image.Resampling.LANCZOS)
    img.paste(face_resized, (80, 160))

    draw.rectangle([80, 160, 320, 460], outline=(148, 163, 184), width=2)

    fields_x = 370
    start_y = 160
    gap_y = 65

    fields_data = [
        f'Name: {name}',
        f'Passport No: {doc_number}',
        f'Nationality: {nationality}',
        f'Date of Birth: {dob}',
        f'Sex: {gender}',
        f'Date of Expiry: {expiry}',
    ]

    for i, line_text in enumerate(fields_data):
        curr_y = start_y + (i * gap_y)
        draw.text((fields_x, curr_y), line_text, fill=(15, 23, 42))

    mrz_bg_y = 720
    draw.rectangle([0, mrz_bg_y, width, height], fill=(241, 245, 249))
    draw.line([(0, mrz_bg_y), (width, mrz_bg_y)], fill=(203, 213, 225), width=2)

    draw.text((80, 760), mrz_line1, fill=(15, 23, 42))
    draw.text((80, 830), mrz_line2, fill=(15, 23, 42))

    if blur:
        img = img.filter(ImageFilter.GaussianBlur(radius=8))

    return img


def generate_all_samples():
    print('Generating synthetic demo samples in:', OUTPUT_DIR)

    # Case 1: Standard Passport
    case1_doc = draw_passport_page(
        name='ANNA MARIA ERIKSSON',
        doc_number='L898902C',
        nationality='UTO',
        dob='1969-08-06',
        expiry='1994-06-23',
        mrz_line1='P<UTOERIKSSON<<ANNA<MARIA<<<<<<<<<<<<<<<<<<<',
        mrz_line2='L898902C<3UTO6908061F9406236ZE184226B<<<<<14',
        face_seed=1,
        gender='F',
    )
    case1_doc.save(OUTPUT_DIR / 'case1_valid_passport.png')
    case1_selfie = Image.fromarray(cv2.cvtColor(create_synthetic_face(1, 'F'), cv2.COLOR_BGR2RGB))
    case1_selfie.save(OUTPUT_DIR / 'case1_selfie_match.png')

    # Case 2: Blurry / Unreadable
    case2_doc = draw_passport_page(
        name='JOHNATHAN DOE',
        doc_number='P12345678',
        nationality='UTO',
        dob='1985-04-12',
        expiry='2030-04-12',
        mrz_line1='P<UTODOE<<JOHNATHAN<<<<<<<<<<<<<<<<<<<<<<<<<',
        mrz_line2='P123456783UTO8504128M3004128<<<<<<<<<<<<<<<10',
        face_seed=2,
        gender='M',
        blur=True,
    )
    case2_doc.save(OUTPUT_DIR / 'case2_blurry_unreadable.png')

    # Case 3: Invalid MRZ Check Digit (tampered)
    case3_doc = draw_passport_page(
        name='MARIA GARCIA',
        doc_number='A12345678',
        nationality='UTO',
        dob='1990-01-15',
        expiry='2030-01-15',
        mrz_line1='P<UTOGARCIA<<MARIA<<<<<<<<<<<<<<<<<<<<<<<<<<',
        mrz_line2='A123456789UTO9001155F3001155<<<<<<<<<<<<<<<99',
        face_seed=3,
        gender='F',
    )
    case3_doc.save(OUTPUT_DIR / 'case3_invalid_mrz_checksum.png')

    # Case 4: Watchlist Blacklisted
    case4_doc = draw_passport_page(
        name='VIKTOR KORZHOV',
        doc_number='B7654321',
        nationality='UTO',
        dob='1978-11-20',
        expiry='2027-11-20',
        mrz_line1='P<UTOKORZHOV<<VIKTOR<<<<<<<<<<<<<<<<<<<<<<<<',
        mrz_line2='B7654321<1UTO7811207M2711209<<<<<<<<<<<<<<<8',
        face_seed=4,
        gender='M',
    )
    case4_doc.save(OUTPUT_DIR / 'case4_watchlist_blacklisted.png')

    # Case 5: Face Mismatch
    case5_doc = draw_passport_page(
        name='ELENA ROSTOVA',
        doc_number='E9988776',
        nationality='UTO',
        dob='1995-09-30',
        expiry='2031-09-30',
        mrz_line1='P<UTOROSTOVA<<ELENA<<<<<<<<<<<<<<<<<<<<<<<<<',
        mrz_line2='E9988776<8UTO9509300F3109306<<<<<<<<<<<<<<<2',
        face_seed=5,
        gender='F',
    )
    case5_doc.save(OUTPUT_DIR / 'case5_face_mismatch_doc.png')
    case5_selfie = Image.fromarray(cv2.cvtColor(create_synthetic_face(8, 'M'), cv2.COLOR_BGR2RGB))
    case5_selfie.save(OUTPUT_DIR / 'case5_face_mismatch_selfie.png')

    # Case 6: Forged VIZ vs MRZ
    case6_doc = draw_passport_page(
        name='FORGED ARTHUR PENDLETON',
        doc_number='L898902C',
        nationality='UTO',
        dob='1982-12-25',
        expiry='1994-06-23',
        mrz_line1='P<UTOERIKSSON<<ANNA<MARIA<<<<<<<<<<<<<<<<<<<',
        mrz_line2='L898902C<3UTO6908061F9406236ZE184226B<<<<<14',
        face_seed=6,
        gender='M',
    )
    case6_doc.save(OUTPUT_DIR / 'case6_forged_viz_mrz_mismatch.png')

    print('Demo samples generated successfully.')


if __name__ == '__main__':
    generate_all_samples()
