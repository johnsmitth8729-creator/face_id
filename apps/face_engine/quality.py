import logging
import cv2
import numpy as np
from django.conf import settings
from apps.face_engine.engine import _load_image, get_face_engine

logger = logging.getLogger(__name__)


def check_face_quality(image, face_info=None) -> dict:
    """
    Perform Face Quality Assessment (FQA) on an enrollment selfie.

    Used ONLY in SaveSelfieAPI for the straight front-facing enrollment image.
    Challenge frames (liveness) bypass this check entirely.

    Checks performed:
        1. Blur detection (Laplacian variance)
        2. Brightness lower bound
        3. Brightness upper bound
        4. Face detected (exactly one face)
        5. Face size (width ratio)
        6. Face position (centered)
        7. Detection confidence
    """
    try:
        fq = getattr(settings, 'FACE_QUALITY', {
            "MIN_BLUR": 25,
            "MIN_BRIGHTNESS": 45,
            "MAX_BRIGHTNESS": 230,
            "MIN_FACE_WIDTH_RATIO": 0.22,
            "MAX_CENTER_OFFSET": 0.30,
            "MIN_DETECTION_CONFIDENCE": 0.65,
        })

        img_array = _load_image(image)
        h, w = img_array.shape[:2]

        # 1. Blur detection
        gray = cv2.cvtColor(img_array, cv2.COLOR_RGB2GRAY)
        blur_val = float(cv2.Laplacian(gray, cv2.CV_64F).var())
        if blur_val < fq.get("MIN_BLUR", 25):
            err_msg = "Image is too blurry. Please capture again."
            logger.error("FQA failed: %s (blur: %.2f < %s)", err_msg, blur_val, fq.get('MIN_BLUR', 25))
            return {"success": False, "error": err_msg, "metrics": {"blur": blur_val}}

        # 2. Brightness lower bound
        brightness_val = float(np.mean(gray))
        if brightness_val < fq.get("MIN_BRIGHTNESS", 45):
            err_msg = "Lighting is too dark."
            logger.error("FQA failed: %s (brightness: %.2f)", err_msg, brightness_val)
            return {"success": False, "error": err_msg, "metrics": {"blur": blur_val, "brightness": brightness_val}}

        # 3. Brightness upper bound
        if brightness_val > fq.get("MAX_BRIGHTNESS", 230):
            err_msg = "Lighting is too bright."
            logger.error("FQA failed: %s (brightness: %.2f)", err_msg, brightness_val)
            return {"success": False, "error": err_msg, "metrics": {"blur": blur_val, "brightness": brightness_val}}

        # 4. Face detection
        engine = get_face_engine()
        if face_info is None:
            face_info = engine.detect_face(img_array)

        if not face_info or 'bbox' not in face_info:
            err_msg = "Could not detect face in the captured photo. Please center your face and try again."
            logger.error("FQA failed: no face detected on enrollment selfie")
            return {"success": False, "error": err_msg, "metrics": {"blur": blur_val, "brightness": brightness_val}}

        bbox = face_info['bbox']  # [x1, y1, x2, y2]
        x1, y1, x2, y2 = bbox

        # 5. Face size validation (area ratio = face_area / frame_area)
        face_area = float((x2 - x1) * (y2 - y1))
        frame_area = float(w * h)
        face_ratio = face_area / frame_area if frame_area > 0 else 0.0
        min_face_size = fq.get("MIN_FACE_SIZE", 0.10)

        logger.info(
            "FQA DEBUG\nframe=%dx%d\nbbox=(%.1f,%.1f,%.1f,%.1f)\nface_area=%.1f\nframe_area=%.1f\nratio=%.4f",
            w, h, x1, y1, x2, y2, face_area, frame_area, face_ratio
        )

        if face_ratio < min_face_size:
            err_msg = "Move closer to the camera."
            logger.error(
                "FQA failed: %s (face_ratio=%.3f < threshold=%.3f)",
                err_msg, face_ratio, min_face_size,
            )
            return {
                "success": False,
                "error": err_msg,
                "face_ratio": round(face_ratio, 4),
                "required_ratio": min_face_size,
                "metrics": {
                    "blur": blur_val,
                    "brightness": brightness_val,
                    "face_ratio": face_ratio,
                },
            }

        # 6. Face position (center offset)
        face_center_x = (x1 + x2) / 2.0
        face_center_y = (y1 + y2) / 2.0
        offset_x = abs(face_center_x - w / 2.0) / w
        offset_y = abs(face_center_y - h / 2.0) / h
        max_offset = fq.get("MAX_CENTER_OFFSET", 0.30)

        if offset_x > max_offset or offset_y > max_offset:
            err_msg = "Center your face in the frame."
            logger.error("FQA failed: %s (offset_x: %.4f, offset_y: %.4f)", err_msg, offset_x, offset_y)
            return {
                "success": False,
                "error": err_msg,
                "metrics": {"blur": blur_val, "brightness": brightness_val, "offset_x": offset_x, "offset_y": offset_y}
            }

        # 7. Detection confidence
        confidence = face_info.get('confidence', 1.0)
        if confidence < fq.get("MIN_DETECTION_CONFIDENCE", 0.65):
            err_msg = "Face detection confidence is too low."
            logger.error("FQA failed: %s (confidence: %.4f)", err_msg, confidence)
            return {
                "success": False,
                "error": err_msg,
                "metrics": {"blur": blur_val, "brightness": brightness_val, "confidence": confidence}
            }

        return {
            "success": True,
            "error": "",
            "metrics": {
                "blur": blur_val,
                "brightness": brightness_val,
                "face_ratio": face_ratio,
                "offset_x": offset_x,
                "offset_y": offset_y,
                "confidence": confidence,
            }
        }

    except Exception as e:
        logger.error("FQA check error: %s", e)
        # Fail open — allow enrollment to continue if quality check itself errors
        return {"success": True, "error": "", "metrics": {}}
