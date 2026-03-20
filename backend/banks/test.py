import warnings
warnings.filterwarnings("ignore")
os.environ["CUDA_VISIBLE_DEVICES"] = ""

import os
import pdfplumber
from pdf2image import convert_from_path
import numpy as np
import cv2

# PaddleOCR is NOT imported here — only loaded if scanned PDF detected
_ocr = None

def _get_ocr():
    global _ocr
    if _ocr is None:
        from paddleocr import PaddleOCR          # ← import only happens here
        _ocr = PaddleOCR(use_angle_cls=False, lang="en", use_gpu=False, show_log=False)
    return _ocr


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
    gray  = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    return gray


def run_ocr(img):
    processed = preprocess(img)
    result    = _get_ocr().ocr(processed, cls=False)
    lines     = []
    if result and result[0]:
        for line in result[0]:
            if line and len(line) >= 2:
                text = line[1][0].strip()
                if text:
                    lines.append(text)
    return lines


def extract_text_from_pdf(pdf_path):
    # Digital PDF — fast path, OCR never loads
    text_lines = extract_pdf_text_fast(pdf_path)
    if text_lines and len(text_lines) > 20:
        return text_lines

    # Scanned PDF — only NOW does PaddleOCR load
    images    = convert_from_path(pdf_path, dpi=150)
    all_lines = []
    for img in images:
        all_lines.extend(run_ocr(img))
    return all_lines
