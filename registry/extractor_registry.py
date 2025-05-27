from extractors.haskell_extractor import HaskellComponentExtractor
from extractors.python_extractor import PythonComponentExtractor

def get_extractor(language: str):
    lang = language.lower()
    if lang == "haskell":
        return HaskellComponentExtractor()
    if lang == "python":
        return PythonComponentExtractor()
    raise ValueError(f"No extractor for language: {language}")
