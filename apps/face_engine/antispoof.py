import os
import logging
import cv2
import numpy as np
from django.conf import settings
from apps.face_engine.engine import _load_image, get_face_engine

logger = logging.getLogger(__name__)


class MiniFASNetSession:
    _instance = None
    _session = None
    _initialized = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def initialize(self):
        if not self._initialized:
            # Skip if mock mode is active
            if settings.AI_ENGINE.get('MODE', 'mock') == 'mock':
                self._initialized = True
                return

            try:
                import onnxruntime as ort

                # Retrieve configured model path
                as_settings = getattr(settings, 'ANTI_SPOOF', {})
                default_path = os.path.join(os.path.dirname(__file__), 'models', 'MiniFASNetV2.onnx')
                model_path = as_settings.get('MODEL_PATH', default_path)

                if not os.path.exists(model_path):
                    err_msg = f"Anti-spoofing model weights file not found at: {model_path}"
                    logger.error(err_msg)
                    raise FileNotFoundError(err_msg)

                # Load ONNX session
                providers = settings.AI_ENGINE.get('ONNX_PROVIDERS', ['CPUExecutionProvider'])
                self._session = ort.InferenceSession(model_path, providers=providers)
                logger.info(f"MiniFASNet ONNX InferenceSession successfully loaded from {model_path}")
                self._initialized = True
            except Exception as e:
                logger.error(f"Failed to initialize MiniFASNet session: {e}")
                self._initialized = True
                self._session = None

    def get_session(self):
        self.initialize()
        return self._session


def check_spoof(image, face_info: dict | None = None, face_count: int | None = None) -> dict:
    """
    Check if the face image is live (real) or spoof (photo, screen, monitor).
    Uses MiniFASNet ONNX model locally.
    """
    # 1. Mock mode bypass
    if settings.AI_ENGINE.get('MODE', 'mock') == 'mock':
        return {
            "success": True,
            "is_live": True,
            "score": 0.98,
            "message": ""
        }

    try:
        img_array = _load_image(image)
        h, w = img_array.shape[:2]
        img_bgr = cv2.cvtColor(img_array, cv2.COLOR_RGB2BGR)

        if face_count is not None and face_count == 0:
            return {
                "success": False,
                "is_live": False,
                "score": 0.0,
                "message": "Zero faces detected. Please make sure your face is visible."
            }
        if face_count is not None and face_count > 1:
            return {
                "success": False,
                "is_live": False,
                "score": 0.0,
                "message": "Multiple faces detected. Only one face must be visible."
            }
        if not face_info:
            # 2. Pre-validation: Face detection to check count if caller did not provide it.
            from apps.face_engine.engine import InsightFaceEngine
            engine = get_face_engine()

            if not isinstance(engine, InsightFaceEngine):
                return {
                    "success": True,
                    "is_live": True,
                    "score": 0.98,
                    "message": ""
                }

            app = engine._get_app()
            faces = app.get(img_bgr)

            if not faces or len(faces) == 0:
                return {
                    "success": False,
                    "is_live": False,
                    "score": 0.0,
                    "message": "Zero faces detected. Please make sure your face is visible."
                }
            if len(faces) > 1:
                return {
                    "success": False,
                    "is_live": False,
                    "score": 0.0,
                    "message": "Multiple faces detected. Only one face must be visible."
                }
            bbox = faces[0].bbox.astype(int)
        else:
            bbox = np.asarray(face_info.get('bbox'), dtype=np.int32)

        # 3. Model initialization check
        session_manager = MiniFASNetSession()
        session = session_manager.get_session()

        as_settings = getattr(settings, 'ANTI_SPOOF', {})
        default_path = os.path.join(os.path.dirname(__file__), 'models', 'MiniFASNetV2.onnx')
        model_path = as_settings.get('MODEL_PATH', default_path)

        if session is None:
            return {
                "success": False,
                "is_live": False,
                "score": 0.0,
                "message": f"Anti-spoofing initialization failed: Model file not found at {model_path}."
            }

        # 4. Anti-spoofing inference on the single face crop
        x1, y1, x2, y2 = bbox

        x1_c = max(0, x1)
        y1_c = max(0, y1)
        x2_c = min(w, x2)
        y2_c = min(h, y2)

        face_crop = img_bgr[y1_c:y2_c, x1_c:x2_c]
        if face_crop.size == 0:
            return {
                "success": False,
                "is_live": False,
                "score": 0.0,
                "message": "Invalid face bounding box cropped."
            }

        # Resize to 80x80 (input size of MiniFASNetV2)
        img_resized = cv2.resize(face_crop, (80, 80))
        img_float = img_resized.astype(np.float32) / 255.0

        # Transpose to CHW (3, 80, 80) and add batch dimensions: (1, 3, 80, 80)
        img_chw = np.transpose(img_float, (2, 0, 1))
        img_batch = np.expand_dims(img_chw, axis=0)

        # Run ONNX inference
        input_name = session.get_inputs()[0].name
        ort_outs = session.run(None, {input_name: img_batch})
        output = ort_outs[0][0]  # shape (3,)

        # Softmax computation
        exp_out = np.exp(output - np.max(output))
        probs = exp_out / np.sum(exp_out)
        live_score = float(probs[2])  # index 2 represents live score

        threshold = as_settings.get("LIVE_THRESHOLD", 0.85)
        is_live = live_score >= threshold

        return {
            "success": True,
            "is_live": is_live,
            "score": round(live_score, 4),
            "message": "" if is_live else "Spoof attack detected."
        }

    except Exception as e:
        logger.error(f"check_spoof exception: {e}")
        return {
            "success": False,
            "is_live": False,
            "score": 0.0,
            "message": f"Face anti-spoofing error: {e}"
        }
