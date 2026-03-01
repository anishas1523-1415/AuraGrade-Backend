"""
AuraGrade — Image Pre-processing Middleware
=============================================
Auto-rotate & enhance handwritten answer sheets before they reach the
Gemini Vision API.

Pipeline
────────
1. **Deskew / Auto-Rotate** — Hough Line Transform detects text baseline
   angle; rotates 90° if the image is vertical (common with phone photos).
2. **CLAHE Contrast Enhancement** — Sharpens faded blue/black ink under
   uneven lighting via Contrast Limited Adaptive Histogram Equalization.
3. **De-noise** — Light non-local means denoising preserves fine pen strokes
   while removing camera grain.

All steps are fail-safe: if any step throws, the original bytes pass through
unchanged so the grading pipeline never crashes.
"""

from __future__ import annotations

import cv2
import numpy as np


def deskew_and_enhance(image_bytes: bytes) -> bytes:
    """Rotate a potentially sideways image and boost ink contrast.

    Parameters
    ----------
    image_bytes : bytes
        Raw image data (JPEG, PNG, etc.) from the uploaded file.

    Returns
    -------
    bytes
        Processed JPEG bytes ready for the Gemini API.
    """
    try:
        nparr = np.frombuffer(image_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if img is None:
            return image_bytes

        # ── 1. Detect orientation via text baselines ──────────────
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        edges = cv2.Canny(gray, 50, 150, apertureSize=3)
        lines = cv2.HoughLinesP(
            edges, 1, np.pi / 180, 100,
            minLineLength=100, maxLineGap=10,
        )

        if lines is not None and len(lines) > 0:
            angles = []
            for line in lines:
                x1, y1, x2, y2 = line[0]
                angle = np.arctan2(y2 - y1, x2 - x1) * 180.0 / np.pi
                angles.append(angle)

            median_angle = float(np.median(angles))

            # If dominant angle is near ±90° the page is sideways
            if abs(median_angle) > 45:
                if median_angle > 0:
                    img = cv2.rotate(img, cv2.ROTATE_90_CLOCKWISE)
                else:
                    img = cv2.rotate(img, cv2.ROTATE_90_COUNTERCLOCKWISE)
            elif abs(median_angle) > 2:
                # Small skew — fine-rotate to straighten
                h, w = img.shape[:2]
                center = (w // 2, h // 2)
                M = cv2.getRotationMatrix2D(center, median_angle, 1.0)
                img = cv2.warpAffine(
                    img, M, (w, h),
                    flags=cv2.INTER_LINEAR,
                    borderMode=cv2.BORDER_REPLICATE,
                )

        # ── 2. CLAHE contrast enhancement ─────────────────────────
        #   Converts to LAB colour space so we only enhance Luminance
        #   without distorting ink colour.  Makes blue/black ink pop
        #   on white notebook paper.
        lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
        l_ch, a_ch, b_ch = cv2.split(lab)
        clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
        l_ch = clahe.apply(l_ch)
        enhanced = cv2.merge((l_ch, a_ch, b_ch))
        img = cv2.cvtColor(enhanced, cv2.COLOR_LAB2BGR)

        # ── 3. Light de-noise (preserve fine pen strokes) ─────────
        img = cv2.fastNlMeansDenoisingColored(img, h=6, hForColorComponents=6)

        # ── 4. Encode as high-quality JPEG ────────────────────────
        ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 95])
        if ok:
            return buf.tobytes()
        return image_bytes

    except Exception:
        # Never crash the pipeline — return original image untouched
        return image_bytes
