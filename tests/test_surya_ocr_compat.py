from __future__ import annotations

from unittest.mock import MagicMock, patch

from ipfs_datasets_py.processors.specialized.pdf.ocr_engine import SuryaOCR


def test_surya_ocr_initializes_with_submodule_predictors() -> None:
    detection_module = MagicMock()
    foundation_module = MagicMock()
    recognition_module = MagicMock()
    detection_instance = MagicMock()
    foundation_instance = MagicMock()
    recognition_instance = MagicMock()
    detection_module.DetectionPredictor.return_value = detection_instance
    foundation_module.FoundationPredictor.return_value = foundation_instance
    recognition_module.RecognitionPredictor.return_value = recognition_instance

    def fake_import_module(name: str):
        if name == "surya.detection":
            return detection_module
        if name == "surya.foundation":
            return foundation_module
        if name == "surya.recognition":
            return recognition_module
        raise ImportError(name)

    with patch("ipfs_datasets_py.processors.specialized.pdf.ocr_engine.surya", MagicMock()):
        with patch("ipfs_datasets_py.processors.specialized.pdf.ocr_engine.importlib.import_module", side_effect=fake_import_module):
            engine = SuryaOCR()

    assert engine.is_available() is True
    assert engine.detection_predictor is detection_instance
    assert engine.foundation_predictor is foundation_instance
    assert engine.recognition_predictor is recognition_instance
    recognition_module.RecognitionPredictor.assert_called_once_with(foundation_instance)