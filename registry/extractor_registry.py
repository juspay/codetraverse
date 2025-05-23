# registry/extractor_registry.py
from extractors.haskell_extractor import HaskellComponentExtractor

def get_extractor(language: str):
    if language.lower() == "haskell":
        return HaskellComponentExtractor()
    raise ValueError(f"No extractor for language: {language}")
