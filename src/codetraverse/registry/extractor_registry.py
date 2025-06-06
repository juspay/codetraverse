from codetraverse.extractors.haskell_extractor import HaskellComponentExtractor
from codetraverse.extractors.python_extractor import PythonComponentExtractor
from codetraverse.extractors.rescript_extractor import RescriptComponentExtractor

def get_extractor(language: str):
    lang = language.lower()
    if lang == "haskell":
        return HaskellComponentExtractor()
    if lang == "python":
        return PythonComponentExtractor()
    if lang == "rescript":
        return RescriptComponentExtractor()
    raise ValueError(f"No extractor for language: {language}")
