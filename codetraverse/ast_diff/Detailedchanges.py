from collections import defaultdict

from collections import defaultdict

class DetailedChanges:
    """A generic data class to hold the results of a diff operation for any language."""

    def __init__(self, module_name: str):
        self.moduleName = module_name
        self.changes = defaultdict(lambda: defaultdict(list))  # {category: {change_type: [items]}}

    def add_change(self, category: str, change_type: str, data: tuple):
        """Adds a change to the appropriate category and type."""
        self.changes[category][change_type].append(data)

    def to_dict(self) -> dict:
        """Flattens the internal structure to keys like addedFunctions, modifiedTypes, etc."""
        output = {"moduleName": self.moduleName}

        for category, change_types in self.changes.items():
            capitalized = category[0].upper() + category[1:]  # e.g., functions → Functions
            for change_type, entries in change_types.items():
                key = f"{change_type}{capitalized}"
                output[key] = entries

        return output

    def __str__(self) -> str:
        summary = [f"Module: {self.moduleName}"]
        for category in sorted(self.changes.keys()):
            changes = self.changes[category]
            added = len(changes.get('added', []))
            modified = len(changes.get('modified', []))
            deleted = len(changes.get('deleted', []))
            if added or modified or deleted:
                summary.append(f"{category}: +{added} ~{modified} -{deleted}")
        return "\n".join(summary)
