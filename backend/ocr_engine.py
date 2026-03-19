from concurrent.futures import ThreadPoolExecutor
from paddleocr import PaddleOCR
from pdf2image import convert_from_path
import numpy as np
import cv2
import pdfplumber

ocr = PaddleOCR(use_angle_cls=False, lang="en", use_gpu=False)

def extract_pdf_text_fast(pdf_path):

    lines = []

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                lines.extend(text.split("\n"))

    return lines

def preprocess(image):
    image = cv2.resize(np.array(image), None, fx=0.6, fy=0.6)
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    return gray


def run_ocr(img):

    processed = preprocess(img)

    result = ocr.ocr(processed, cls=False)

    lines = []
    for line in result[0]:
        lines.append(line[1][0])

    return lines


def extract_text_from_pdf(pdf_path):
    text_lines = extract_pdf_text_fast(pdf_path)
    if text_lines and len(text_lines) > 20:
        return text_lines
    
    images = convert_from_path(pdf_path, dpi=150)

    with ThreadPoolExecutor(max_workers=4) as executor:
        results = list(executor.map(run_ocr, images))

    all_lines = []

    for page_lines in results:
        all_lines.extend(page_lines)

    return all_lines