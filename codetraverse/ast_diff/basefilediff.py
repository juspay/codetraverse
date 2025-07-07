
from abc import abstractmethod, ABC
from typing import Any, Dict
from Detailedchanges import DetailedChanges
from tree_sitter import Language, Parser, Node


class BaseFileDiff(ABC):

    def __init__(self, module_name: str):
        self.changes = DetailedChanges(module_name)

    @abstractmethod
    def get_decl_name(self, node: Node) -> str:
        pass

    @abstractmethod
    def extract_components(self, root: Node) -> Dict[str, Dict]:
        pass

    @abstractmethod
    def diff_components(self, before_map: dict, after_map: dict) -> Dict[str, Any]:
        pass

    @abstractmethod
    def compare_two_files(self, old_ast: Node, new_ast: Node) -> DetailedChanges:
        pass
    
    @abstractmethod
    def process_single_file(self, ast: Node, mode: str) -> DetailedChanges:

        print(f"Warning: process_single_file not implemented for {self.__class__.__name__}. No changes will be reported for added/deleted files.")
        return self.changes