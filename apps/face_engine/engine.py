"""
AKHU AFIVS — Face Engine
InsightFace/ArcFace integration with mock fallback for development.

In production: AI_ENGINE_MODE=insightface
In development: AI_ENGINE_MODE=mock
"""
import io
import logging
import hashlib
import random
import threading
from typing import Optional, Tuple
from pathlib import Path

import numpy as np
from PIL import Image
from django.conf import settings

logger = logging.getLogger(__name__)


def _load_image(source) -> np.ndarray:
    """Convert various image sources to numpy array (RGB)."""
    if isinstance(source, np.ndarray):
        return source
    if isinstance(source, (str, Path)):
        img = Image.open(source).convert('RGB')
    elif hasattr(source, 'read'):
        img = Image.open(io.BytesIO(source.read())).convert('RGB')
    elif isinstance(source, bytes):
        img = Image.open(io.BytesIO(source)).convert('RGB')
    else:
        img = source.convert('RGB') if hasattr(source, 'convert') else Image.fromarray(source)
    return np.array(img)


def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Compute cosine similarity between two vectors."""
    a = np.array(a, dtype=np.float32)
    b = np.array(b, dtype=np.float32)
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(np.dot(a, b) / (norm_a * norm_b))


def _similarity_to_percentage(cosine_sim: float) -> float:
    """Map cosine similarity to 0-100% range for InsightFace ArcFace normed embeddings.
    Calibrated so that:
      - cosine_sim >= 0.30 → ~90%+ (verified)
      - cosine_sim ~0.24   → ~80%  (review boundary)
      - cosine_sim < 0.10  → <40%  (clear mismatch)
    """
    if cosine_sim <= 0.10:
        return max(0.0, round(30.0 + (max(0.0, cosine_sim) / 0.10) * 10.0, 2))
    elif cosine_sim <= 0.18:
        pct = 40.0 + (cosine_sim - 0.10) / 0.08 * 25.0
        return round(pct, 2)
    elif cosine_sim <= 0.24:
        pct = 65.0 + (cosine_sim - 0.18) / 0.06 * 17.0
        return round(pct, 2)
    elif cosine_sim <= 0.30:
        pct = 82.0 + (cosine_sim - 0.24) / 0.06 * 10.0
        return round(pct, 2)
    else:
        pct = 92.0 + min(8.0, (cosine_sim - 0.30) / 0.20 * 8.0)
        return round(pct, 2)


def similarity_to_percentage(cosine_sim: float) -> float:
    """Public wrapper for converting a cosine score to the configured UI scale."""
    return _similarity_to_percentage(cosine_sim)


def _resize_if_large(img: np.ndarray, max_dim: int = 640) -> np.ndarray:
    """Resize image if its dimensions exceed max_dim, keeping aspect ratio."""
    try:
        import cv2
        h, w = img.shape[:2]
        if max(h, w) > max_dim:
            scale = max_dim / max(h, w)
            new_w = int(w * scale)
            new_h = int(h * scale)
            return cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_AREA)
    except Exception as e:
        logger.warning(f"Could not resize image: {e}")
    return img


class MockFaceEngine:
    """
    Mock engine for development/testing without InsightFace models.
    Returns deterministic results based on image hashes for consistency.
    """

    def detect_face(self, image) -> Optional[dict]:
        """Returns a fake detection result."""
        img_array = _load_image(image)
        h, w = img_array.shape[:2]
        return {
            'bbox': [w // 4, h // 4, 3 * w // 4, 3 * h // 4],
            'confidence': 0.98,
            'landmarks': [],
        }

    def extract_embedding(self, image) -> Optional[np.ndarray]:
        """Returns a pseudo-embedding containing a downscaled representation of the face/image."""
        try:
            img_array = _load_image(image)
            import cv2
            gray = cv2.cvtColor(img_array, cv2.COLOR_RGB2GRAY)
            # Resize to 16x16 to get 256 pixels
            small = cv2.resize(gray, (16, 16), interpolation=cv2.INTER_AREA)
            pixel_vec = small.flatten().astype(np.float32) / 255.0
            
            # Use deterministic hash for the remaining 256 dimensions
            img_bytes = img_array.tobytes()
            hash_val = hashlib.sha256(img_bytes).hexdigest()
            seed = int(hash_val[:8], 16)
            rng = np.random.RandomState(seed)
            random_vec = rng.randn(256).astype(np.float32) * 0.1
            
            # Combine into 512-dim vector
            embedding = np.concatenate([pixel_vec, random_vec])
            # Normalize to unit vector
            embedding = embedding / np.linalg.norm(embedding)
            return embedding
        except Exception as e:
            logger.warning(f"Mock extract_embedding failed, falling back to random: {e}")
            rng = np.random.RandomState(42)
            embedding = rng.randn(512).astype(np.float32)
            return embedding / np.linalg.norm(embedding)

    def extract_face_and_embedding(self, image, require_single: bool = False) -> dict:
        face = self.detect_face(image)
        embedding = self.extract_embedding(image)
        return {
            'success': embedding is not None,
            'face_count': 1 if embedding is not None else 0,
            'face': face,
            'embedding': embedding,
            'error': '' if embedding is not None else 'No face detected',
        }

    def compare_faces(self, embedding1, embedding2) -> Tuple[float, float]:
        """
        Returns (cosine_similarity, match_percentage).
        In mock mode, calculates similarity based on the embedded 16x16 image features.
        """
        if embedding1 is None or embedding2 is None:
            return 0.0, 0.0
        e1 = np.array(embedding1, dtype=np.float32)
        e2 = np.array(embedding2, dtype=np.float32)
        
        # Extract the 16x16 pixel vector (first 256 dimensions)
        p1 = e1[:256]
        p2 = e2[:256]
        
        # Calculate cosine similarity of the pixel vectors
        norm_p1 = np.linalg.norm(p1)
        norm_p2 = np.linalg.norm(p2)
        if norm_p1 == 0 or norm_p2 == 0:
            sim = 0.0
        else:
            sim = float(np.dot(p1, p2) / (norm_p1 * norm_p2))
            
        # Calibrate similarity to match percentage:
        # Since pixel values are all positive, their cosine similarity is usually high (between 0.70 and 1.0).
        # We scale:
        #   - sim >= 0.97 -> 90% - 99% (match)
        #   - sim < 0.97 -> less than 50% (mismatch)
        if sim >= 0.975:
            percentage = 90.0 + (sim - 0.975) / 0.025 * 9.0 + random.uniform(-0.5, 0.5)
            percentage = min(99.9, max(90.0, percentage))
        else:
            percentage = 15.0 + (sim / 0.975) * 35.0 + random.uniform(-2.0, 2.0)
            percentage = min(75.0, max(5.0, percentage))
            
        return sim, percentage


class InsightFaceEngine:
    """
    Production face engine using InsightFace (ArcFace model).
    Requires: pip install insightface onnxruntime
    Models are downloaded automatically on first use.
    """
    _instance = None
    _instance_lock = threading.Lock()
    _app = None
    _app_lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def _get_app(self):
        if self._app is None:
            with self._app_lock:
                # Double-checked locking: re-check after acquiring lock
                if self._app is None:
                    try:
                        import insightface
                        from insightface.app import FaceAnalysis
                        ai_settings = settings.AI_ENGINE
                        app = FaceAnalysis(
                            name=ai_settings.get('MODEL_PACK', 'buffalo_l'),
                            providers=ai_settings.get('ONNX_PROVIDERS', ['CPUExecutionProvider']),
                        )
                        app.prepare(ctx_id=0, det_size=(640, 640))
                        self._app = app
                        logger.info('InsightFace engine initialized successfully')
                    except Exception as e:
                        logger.error(f'Failed to initialize InsightFace: {e}')
                        raise RuntimeError(f'InsightFace initialization failed: {e}')
        return self._app

    def detect_face(self, image) -> Optional[dict]:
        """Detect face and return bounding box + landmarks, mapped back to the original image dimensions."""
        try:
            import cv2
            img_array = _load_image(image)
            h_orig, w_orig = img_array.shape[:2]

            img_resized = _resize_if_large(img_array)
            h_res, w_res = img_resized.shape[:2]

            img_bgr = cv2.cvtColor(img_resized, cv2.COLOR_RGB2BGR)
            app = self._get_app()
            faces = app.get(img_bgr)
            if not faces:
                logger.warning('No face detected in InsightFaceEngine')
                return None
            face = faces[0]

            bbox = face.bbox.tolist()
            landmarks = face.kps.tolist() if face.kps is not None else []

            # If the image was resized for detection, scale the coordinates back to original size
            if h_res != h_orig or w_res != w_orig:
                scale_x = float(w_orig) / float(w_res)
                scale_y = float(h_orig) / float(h_res)
                bbox = [
                    bbox[0] * scale_x,
                    bbox[1] * scale_y,
                    bbox[2] * scale_x,
                    bbox[3] * scale_y
                ]
                if landmarks:
                    landmarks = [[kp[0] * scale_x, kp[1] * scale_y] for kp in landmarks]

            return {
                'bbox': bbox,
                'confidence': float(face.det_score),
                'landmarks': landmarks,
            }
        except Exception as e:
            logger.error(f'Face detection error: {e}')
            return None

    def _get_faces_once(self, image):
        import cv2
        img_array = _resize_if_large(_load_image(image))
        img_bgr = cv2.cvtColor(img_array, cv2.COLOR_RGB2BGR)
        return self._get_app().get(img_bgr)

    def extract_face_and_embedding(self, image, require_single: bool = False) -> dict:
        """Run InsightFace once and return face metadata plus embedding."""
        try:
            import cv2
            img_array = _load_image(image)
            h_orig, w_orig = img_array.shape[:2]
            img_resized = _resize_if_large(img_array)
            h_res, w_res = img_resized.shape[:2]
            img_bgr = cv2.cvtColor(img_resized, cv2.COLOR_RGB2BGR)
            faces = self._get_app().get(img_bgr)
            face_count = len(faces)
            if face_count == 0:
                return {
                    'success': False,
                    'face_count': 0,
                    'face': None,
                    'embedding': None,
                    'error': 'No face detected',
                }
            if require_single and face_count != 1:
                return {
                    'success': False,
                    'face_count': face_count,
                    'face': None,
                    'embedding': None,
                    'error': 'Multiple faces detected',
                }

            face = faces[0]
            bbox = face.bbox.tolist()
            landmarks = face.kps.tolist() if face.kps is not None else []
            if h_res != h_orig or w_res != w_orig:
                scale_x = float(w_orig) / float(w_res)
                scale_y = float(h_orig) / float(h_res)
                bbox = [bbox[0] * scale_x, bbox[1] * scale_y, bbox[2] * scale_x, bbox[3] * scale_y]
                if landmarks:
                    landmarks = [[kp[0] * scale_x, kp[1] * scale_y] for kp in landmarks]
            face_meta = {
                'bbox': bbox,
                'confidence': float(face.det_score),
                'landmarks': landmarks,
            }
            return {
                'success': True,
                'face_count': face_count,
                'face': face_meta,
                'embedding': face.normed_embedding.astype(np.float32),
                'error': '',
            }
        except Exception as e:
            logger.error(f'Face + embedding extraction error: {e}')
            return {
                'success': False,
                'face_count': 0,
                'face': None,
                'embedding': None,
                'error': str(e),
            }

    def extract_embedding(self, image) -> Optional[np.ndarray]:
        """Extract 512-dim ArcFace embedding from image."""
        try:
            import cv2
            img_array = _load_image(image)
            img_array = _resize_if_large(img_array)
            img_bgr = cv2.cvtColor(img_array, cv2.COLOR_RGB2BGR)
            app = self._get_app()
            faces = app.get(img_bgr)
            if not faces:
                logger.warning('No face detected for embedding')
                return None
            face = faces[0]
            embedding = face.normed_embedding
            return embedding.astype(np.float32)
        except Exception as e:
            logger.error(f'Embedding extraction error: {e}')
            return None

    def compare_faces(self, embedding1, embedding2) -> Tuple[float, float]:
        """Compare two embeddings. Returns (cosine_sim, match_percentage)."""
        if embedding1 is None or embedding2 is None:
            return 0.0, 0.0
        e1 = np.array(embedding1, dtype=np.float32)
        e2 = np.array(embedding2, dtype=np.float32)
        cosine_sim = _cosine_similarity(e1, e2)
        percentage = _similarity_to_percentage(cosine_sim)
        return cosine_sim, percentage




def get_face_engine():
    """
    Factory function: returns the configured face engine.
    Reads AI_ENGINE_MODE from settings.
    """
    mode = settings.AI_ENGINE.get('MODE', 'mock')
    if mode == 'insightface':
        try:
            return InsightFaceEngine()
        except Exception as e:
            logger.warning(f'InsightFace unavailable, falling back to mock: {e}')
            return MockFaceEngine()
    return MockFaceEngine()


def determine_verification_status(match_percentage: float) -> str:
    """
    Determine verification status from match percentage.
    Returns: 'verified' | 'review_required' | 'rejected'
    """
    thresholds = settings.AI_ENGINE
    verified_threshold = thresholds.get('THRESHOLD_VERIFIED', 0.90) * 100
    review_threshold = thresholds.get('THRESHOLD_REVIEW', 0.80) * 100

    if match_percentage >= verified_threshold:
        return 'verified'
    elif match_percentage >= review_threshold:
        return 'review_required'
    else:
        return 'rejected'
