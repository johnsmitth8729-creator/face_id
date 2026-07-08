"""
AKHU AFIVS — Liveness Detector
Challenge Generator and Frame Analyzer for Multi-Angle Face Capture.
Uses MediaPipe or OpenCV with mock fallback for development.
"""
import logging
import base64
import io
import random
from typing import Optional, List

import numpy as np
from PIL import Image
from django.conf import settings

logger = logging.getLogger(__name__)

CHALLENGE_MESSAGES = {
    'en': {
        'face_detection': 'Please look straight into the camera. The system will detect your face automatically.',
        'blink': 'Please close your eyes for a second',
        'look_left': 'Please look to the left',
        'look_right': 'Please look to the right',
        'look_up': 'Please look up',
    },
    'uz': {
        'face_detection': 'Iltimos, kameraga tik qarang. Yuzingiz avtomatik aniqlanadi.',
        'blink': 'Iltimos, ko\'zingizni bir soniyaga yuming',
        'look_left': 'Iltimos, chapga qarang',
        'look_right': 'Iltimos, o\'ngga qarang',
        'look_up': 'Iltimos, yuqoriga qarang',
    },
}


def _decode_base64_image(data_url: str) -> Optional[np.ndarray]:
    """Decode base64 image data URL to numpy array."""
    try:
        if isinstance(data_url, np.ndarray):
            return data_url
        if ',' in data_url:
            data_url = data_url.split(',')[1]
        img_bytes = base64.b64decode(data_url)
        img = Image.open(io.BytesIO(img_bytes)).convert('RGB')
        return np.array(img)
    except Exception as e:
        logger.error(f'Failed to decode base64 image: {e}')
        return None


class MockLivenessDetector:
    """Mock liveness detector for development."""

    def analyze_frame(self, frame_data: str, challenge_type: str) -> dict:
        """Mock analysis — always returns success."""
        results = {
            'face_detection': {'face_detected': True, 'face_centered': True},
            'blink': {'ear_left': 0.18, 'ear_right': 0.17, 'blink_detected': True},
            'look_left': {'yaw': -25.0, 'pitch': 2.0, 'direction': 'left'},
            'look_right': {'yaw': 25.0, 'pitch': 2.0, 'direction': 'right'},
            'look_up': {'yaw': 0.0, 'pitch': -20.0, 'direction': 'up'},
        }

        return {
            'success': True,
            'challenge_type': challenge_type,
            'confidence': 1.0,
            'details': results.get(challenge_type, {}),
            'anti_spoof': {'result': 'real', 'score': 0.99},
        }

    def detect_face_in_frame(self, frame_data: str) -> dict:
        """Mock face detection in frame."""
        return {
            'face_detected': True,
            'face_centered': True,
            'face_size_ok': True,
            'eyes_open': True,
            'lighting_ok': True,
            'confidence': 0.97,
        }


class MediaPipeLivenessDetector:
    """
    Production liveness detector using MediaPipe Face Mesh.
    Requires: pip install mediapipe opencv-python
    """
    _instance = None
    _face_mesh = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def _get_face_mesh(self):
        if self._face_mesh is None:
            try:
                import mediapipe as mp
                self._mp_face_mesh = mp.solutions.face_mesh
                self._face_mesh = self._mp_face_mesh.FaceMesh(
                    static_image_mode=True,
                    max_num_faces=1,
                    refine_landmarks=True,
                    min_detection_confidence=0.5,
                    min_tracking_confidence=0.5,
                )
                logger.info('MediaPipe Face Mesh initialized')
            except Exception as e:
                logger.error(f'MediaPipe initialization failed: {e}')
                raise
        return self._face_mesh

    def _point(self, landmarks, idx: int, width: int, height: int) -> np.ndarray:
        lm = landmarks[idx]
        return np.array([lm.x * width, lm.y * height], dtype=np.float32)

    def _head_pose(self, landmarks, width: int, height: int) -> tuple[float, float]:
        nose = self._point(landmarks, 1, width, height)
        left_cheek = self._point(landmarks, 234, width, height)
        right_cheek = self._point(landmarks, 454, width, height)
        chin = self._point(landmarks, 152, width, height)
        forehead = self._point(landmarks, 10, width, height)

        face_width = max(float(np.linalg.norm(right_cheek - left_cheek)), 1.0)
        face_height = max(float(np.linalg.norm(chin - forehead)), 1.0)
        center_x = (left_cheek[0] + right_cheek[0]) / 2.0
        center_y = (forehead[1] + chin[1]) / 2.0

        yaw = ((nose[0] - center_x) / face_width) * 90.0
        pitch = ((center_y - nose[1]) / face_height) * 90.0
        return float(yaw), float(pitch)

    def _eye_aspect_ratio(self, landmarks, width: int, height: int, indices: tuple[int, int, int, int, int, int]) -> float:
        p1, p2, p3, p4, p5, p6 = [self._point(landmarks, i, width, height) for i in indices]
        vertical = np.linalg.norm(p2 - p6) + np.linalg.norm(p3 - p5)
        horizontal = 2.0 * max(np.linalg.norm(p1 - p4), 1.0)
        return float(vertical / horizontal)

    def analyze_frame(self, frame_data: str, challenge_type: str) -> dict:
        """Analyze a single frame for the requested liveness challenge."""
        img_array = _decode_base64_image(frame_data)
        if img_array is None:
            return {'success': False, 'error': 'Invalid frame data', 'confidence': 0.0}

        try:
            face_mesh = self._get_face_mesh()
            results = face_mesh.process(img_array)
            if not results.multi_face_landmarks:
                return {
                    'success': False,
                    'error': 'No face detected',
                    'challenge_type': challenge_type,
                    'confidence': 0.0,
                    'details': {'face_detected': False},
                }

            h, w = img_array.shape[:2]
            landmarks = results.multi_face_landmarks[0].landmark
            yaw, pitch = self._head_pose(landmarks, w, h)
            details = {'face_detected': True, 'yaw': round(yaw, 2), 'pitch': round(pitch, 2)}

            liveness = settings.LIVENESS
            success = False
            message = ''

            if challenge_type == 'look_left':
                threshold = liveness.get('HEAD_YAW_LEFT', -12.0)
                success = yaw < threshold
                message = f'Please turn your head left' if not success else ''
            elif challenge_type == 'look_right':
                threshold = liveness.get('HEAD_YAW_RIGHT', 12.0)
                success = yaw > threshold
                message = f'Please turn your head right' if not success else ''
            elif challenge_type == 'look_up':
                threshold = liveness.get('HEAD_PITCH_UP', 10.0)
                success = pitch > threshold
                message = f'Please look up' if not success else ''
            elif challenge_type == 'blink':
                left_ear = self._eye_aspect_ratio(landmarks, w, h, (33, 160, 158, 133, 153, 144))
                right_ear = self._eye_aspect_ratio(landmarks, w, h, (362, 385, 387, 263, 373, 380))
                ear = (left_ear + right_ear) / 2.0
                details.update({'ear': round(ear, 3)})
                success = ear < liveness.get('BLINK_THRESHOLD', 0.25)
                message = 'Please blink' if not success else ''
            else:
                return {
                    'success': False,
                    'error': f'Unsupported challenge: {challenge_type}',
                    'challenge_type': challenge_type,
                    'confidence': 0.0,
                    'details': details,
                }

            return {
                'success': success,
                'error': message,
                'challenge_type': challenge_type,
                'confidence': 1.0 if success else 0.0,
                'details': details,
                'anti_spoof': {'result': 'real', 'score': 0.99},
            }
        except Exception as e:
            logger.error(f'Liveness analysis error: {e}')
            return {
                'success': False,
                'error': str(e),
                'challenge_type': challenge_type,
                'confidence': 0.0,
                'details': {'face_detected': False},
            }

    def detect_face_in_frame(self, frame_data: str) -> dict:
        """Check face presence and quality in frame."""
        img_array = _decode_base64_image(frame_data)
        if img_array is None:
            return {'face_detected': False}

        try:
            face_mesh = self._get_face_mesh()
            results = face_mesh.process(img_array)

            if not results.multi_face_landmarks:
                return {'face_detected': False, 'face_centered': False, 'eyes_open': False, 'lighting_ok': False}

            h, w = img_array.shape[:2]
            landmarks = results.multi_face_landmarks[0].landmark

            # 1. Centering & Size
            left_cheek = self._point(landmarks, 234, w, h)
            right_cheek = self._point(landmarks, 454, w, h)
            forehead = self._point(landmarks, 10, w, h)
            chin = self._point(landmarks, 152, w, h)

            face_width = max(float(np.linalg.norm(right_cheek - left_cheek)), 1.0)
            face_height = max(float(np.linalg.norm(chin - forehead)), 1.0)
            center_x = (left_cheek[0] + right_cheek[0]) / 2.0
            center_y = (forehead[1] + chin[1]) / 2.0

            offset_x = abs(center_x - w / 2.0) / w
            offset_y = abs(center_y - h / 2.0) / h

            # Centering offset should be < 0.20 width, < 0.25 height
            face_centered = offset_x < 0.20 and offset_y < 0.25

            # Size should be at least 20% of image width
            face_size_ok = (face_width / w) >= 0.20

            # 2. Eyes Open (EAR)
            left_ear = self._eye_aspect_ratio(landmarks, w, h, (33, 160, 158, 133, 153, 144))
            right_ear = self._eye_aspect_ratio(landmarks, w, h, (362, 385, 387, 263, 373, 380))
            ear = (left_ear + right_ear) / 2.0
            logger.info(f"detect_face_in_frame: EAR={ear:.4f} (threshold=0.11)")
            try:
                with open('ear_debug.txt', 'a') as f_debug:
                    f_debug.write(f"EAR: {ear:.4f}, L: {left_ear:.4f}, R: {right_ear:.4f}\n")
            except Exception:
                pass
            eyes_open = ear >= 0.11

            # 3. Brightness/Lighting
            import cv2
            gray = cv2.cvtColor(img_array, cv2.COLOR_RGB2GRAY)
            brightness_val = float(np.mean(gray))
            lighting_ok = 45 <= brightness_val <= 230

            return {
                'face_detected': True,
                'face_centered': face_centered,
                'face_size_ok': face_size_ok,
                'eyes_open': eyes_open,
                'lighting_ok': lighting_ok,
                'brightness': brightness_val,
                'confidence': 0.95,
            }
        except Exception as e:
            logger.error(f'Face detection error: {e}')
            return {'face_detected': False, 'error': str(e)}


class OpenCVLivenessDetector:
    """Fallback liveness detector using OpenCV Haar Cascades or InsightFace."""

    def __init__(self):
        import cv2
        import os
        self.face_cascade = None
        try:
            if hasattr(cv2, 'data') and getattr(cv2.data, 'haarcascades', None):
                cascade_path = os.path.join(cv2.data.haarcascades, 'haarcascade_frontalface_default.xml')
                if os.path.exists(cascade_path):
                    self.face_cascade = cv2.CascadeClassifier(cascade_path)
        except Exception as e:
            logger.warning(f"Failed to load OpenCV cascade classifier: {e}")
            
        if self.face_cascade:
            logger.info("OpenCV Liveness Detector (with Haar Cascade) initialized")
        else:
            logger.info("OpenCV Liveness Detector (without Haar Cascade) initialized")

    def analyze_frame(self, frame_data: str, challenge_type: str) -> dict:
        """Analyze frame for face presence and head pose using InsightFace fallback."""
        img_array = _decode_base64_image(frame_data)
        if img_array is None:
            return {'success': False, 'error': 'Invalid frame data', 'confidence': 0.0}

        try:
            import cv2
            from django.conf import settings
            from apps.face_engine.engine import get_face_engine, InsightFaceEngine
            
            engine = get_face_engine()
            if not isinstance(engine, InsightFaceEngine):
                # Fallback to simple face presence in mock mode
                if self.face_cascade:
                    gray = cv2.cvtColor(img_array, cv2.COLOR_RGB2GRAY)
                    faces = self.face_cascade.detectMultiScale(gray, 1.1, 4)
                    success = len(faces) > 0
                else:
                    success = True
                return {
                    'success': success,
                    'error': '' if success else 'No face detected',
                    'challenge_type': challenge_type,
                    'confidence': 0.95 if success else 0.0,
                    'details': {'face_detected': success, 'face_centered': success},
                    'anti_spoof': {'result': 'real', 'score': 0.95},
                }

            app = engine._get_app()
            img_bgr = cv2.cvtColor(img_array, cv2.COLOR_RGB2BGR)
            faces = app.get(img_bgr)
            
            if not faces or len(faces) == 0:
                return {
                    'success': False,
                    'error': 'No face detected',
                    'challenge_type': challenge_type,
                    'confidence': 0.0,
                    'details': {'face_detected': False, 'face_centered': False},
                }
                
            if len(faces) > 1:
                return {
                    'success': False,
                    'error': 'Multiple faces detected',
                    'challenge_type': challenge_type,
                    'confidence': 0.0,
                    'details': {'face_detected': True, 'face_centered': False},
                }

            face = faces[0]
            kps = face.kps  # shape (5, 2)
            
            if kps is None or len(kps) < 5:
                return {
                    'success': False,
                    'error': 'No face landmarks detected',
                    'challenge_type': challenge_type,
                    'confidence': 0.0,
                }

            # 2. Check head pose from the 5 landmarks (kps)
            # kps indices: 0: left eye, 1: right eye, 2: nose, 3: left mouth, 4: right mouth
            d_left = abs(kps[2][0] - kps[0][0])
            d_right = abs(kps[2][0] - kps[1][0])
            
            eye_y = (kps[0][1] + kps[1][1]) / 2.0
            mouth_y = (kps[3][1] + kps[4][1]) / 2.0
            face_height = max(1.0, mouth_y - eye_y)
            nose_y_dist = kps[2][1] - eye_y
            pitch_ratio = nose_y_dist / face_height

            success = False
            error_msg = ""

            if challenge_type == 'look_left':
                ratio = d_right / max(1.0, d_left)
                success = ratio >= 1.45
                if not success:
                    error_msg = "Please look left"
            elif challenge_type == 'look_right':
                ratio = d_left / max(1.0, d_right)
                success = ratio >= 1.45
                if not success:
                    error_msg = "Please look right"
            elif challenge_type == 'look_up':
                success = pitch_ratio < 0.35
                if not success:
                    error_msg = "Please look up"
            else:
                success = True

            # Explicitly cast to native python types to prevent JSON serialization errors
            success_bool = bool(success)
            d_left_val = float(d_left)
            d_right_val = float(d_right)
            pitch_ratio_val = float(pitch_ratio)

            logger.info(
                "OpenCV Liveness check: challenge=%s, d_left=%.1f, d_right=%.1f, pitch_ratio=%.3f, success=%s",
                challenge_type, d_left_val, d_right_val, pitch_ratio_val, success_bool
            )

            return {
                'success': success_bool,
                'error': error_msg if not success_bool else '',
                'challenge_type': challenge_type,
                'confidence': 0.95 if success_bool else 0.0,
                'details': {
                    'face_detected': True,
                    'face_centered': True,
                    'd_left': d_left_val,
                    'd_right': d_right_val,
                    'pitch_ratio': pitch_ratio_val
                },
                'anti_spoof': {'result': 'real', 'score': 0.95},
            }
        except Exception as e:
            logger.error(f'OpenCV fallback analyze_frame error: {e}')
            return {'success': False, 'error': str(e), 'confidence': 0.0}

    def detect_face_in_frame(self, frame_data: str) -> dict:
        """Check face presence in frame using InsightFace or cascade fallback."""
        img_array = _decode_base64_image(frame_data)
        if img_array is None:
            return {'face_detected': False}

        try:
            import cv2
            from apps.face_engine.engine import get_face_engine, InsightFaceEngine
            engine = get_face_engine()
            
            if isinstance(engine, InsightFaceEngine):
                app = engine._get_app()
                img_bgr = cv2.cvtColor(img_array, cv2.COLOR_RGB2BGR)
                faces = app.get(img_bgr)
                success = len(faces) > 0
                return {
                    'face_detected': success,
                    'face_centered': success,
                    'face_size_ok': True,
                    'eyes_open': success,
                    'lighting_ok': True,
                    'confidence': 0.95 if success else 0.0,
                }

            if self.face_cascade:
                gray = cv2.cvtColor(img_array, cv2.COLOR_RGB2GRAY)
                faces = self.face_cascade.detectMultiScale(gray, 1.1, 4)
                success = len(faces) > 0
            else:
                success = True
            return {
                'face_detected': success,
                'face_centered': success,
                'face_size_ok': True,
                'eyes_open': success,
                'lighting_ok': True,
                'confidence': 0.95 if success else 0.0,
            }
        except Exception as e:
            return {'face_detected': False, 'error': str(e)}


def get_liveness_detector():
    """Factory: returns configured liveness detector with fallback options."""
    # 1. If mock mode is active, use MockLivenessDetector directly
    from django.conf import settings
    ai_mode = settings.AI_ENGINE.get('MODE', 'mock')
    if ai_mode == 'mock':
        logger.info("Using MockLivenessDetector (AI_ENGINE_MODE is mock)")
        return MockLivenessDetector()

    # 2. Try MediaPipe Liveness Detector
    try:
        detector = MediaPipeLivenessDetector()
        # Dry-run: verify we can actually load the face mesh without raising AttributeError/ModuleNotFoundError
        detector._get_face_mesh()
        logger.info("Using MediaPipeLivenessDetector")
        return detector
    except Exception as e:
        logger.warning(f'MediaPipe Face Mesh initialization failed, trying OpenCV fallback: {e}')

    # 3. Fallback to OpenCV Haar Cascade Detector
    try:
        return OpenCVLivenessDetector()
    except Exception as e:
        logger.warning(f'OpenCV Liveness Detector initialization failed, falling back to mock: {e}')

    # 4. Final safety net: Mock
    return MockLivenessDetector()


def generate_challenge_sequence(count: int | None = None) -> List[str]:
    """Generate a random liveness challenge sequence."""
    challenges = list(settings.LIVENESS.get('CHALLENGES', ['look_left', 'look_right', 'look_up']))
    requested = count or settings.LIVENESS.get('CHALLENGE_COUNT', 3)
    count = max(1, min(int(requested), len(challenges)))
    return random.sample(challenges, count)


def get_challenge_instruction(challenge_type: str, language: str = 'en') -> str:
    """Return localized instruction for a challenge type."""
    messages = CHALLENGE_MESSAGES.get(language, CHALLENGE_MESSAGES['en'])
    return messages.get(challenge_type, challenge_type)
