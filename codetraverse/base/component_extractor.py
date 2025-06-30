from abc import ABC, abstractmethod


class ComponentExtractor(ABC):
    @abstractmethod
    def process_file(self, file_path: str):
        pass

    @abstractmethod
    def write_to_file(self, output_path: str):
        pass

    @abstractmethod
    def extract_all_components(self):
        pass
