from extractors.haskell_extractor import HaskellComponentExtractor
from extractors.python_extractor import PythonComponentExtractor
from extractors.rescript_extractor import RescriptComponentExtractor
from extractors.go_extractor import GoComponentExtractor

def get_extractor(language: str):
    lang = language.lower()
    if lang == "haskell":
        return HaskellComponentExtractor()
    if lang == "python":
        return PythonComponentExtractor()
    if lang == "rescript":
        return RescriptComponentExtractor()
    if lang == "go":
        return GoComponentExtractor()
    raise ValueError(f"No extractor for language: {language}")
