# codetraverse/extractors/cucumber_extractor.py

import os
import json
import re
from codetraverse.base.component_extractor import ComponentExtractor


class CucumberComponentExtractor(ComponentExtractor):
    def __init__(self):
        self.all_components = []

    def parse_file(self, file_path: str):
        with open(file_path, 'r', encoding='utf-8') as f:
            plain = f.read()
        return plain

    def extract_tags(self, line):
        tags = []
        for match in re.finditer(r'@(\w+)', line):
            tags.append("@" + match.group(1))
        return tags if tags else None

    def extract_steps(self, content, start_line):
        steps = []
        step_pattern = r'^\s*((Given|When|Then|And|But)\s+(.+))'
        
        for i, line in enumerate(content.split('\n')):
            match = re.match(step_pattern, line, re.IGNORECASE)
            if match:
                full_step = match.group(1).strip()
                step_type = match.group(2).lower()
                step_text = match.group(3).strip()
                
                steps.append({
                    "type": step_type,
                    "text": step_text,
                    "line": start_line + i
                })
        
        return steps if steps else None

    def extract_examples(self, content, start_line):
        examples = []
        lines = content.split('\n')
        
        in_examples = False
        headers = []
        
        for i, line in enumerate(lines):
            stripped = line.strip()
            
            if stripped.startswith('|') and stripped.endswith('|'):
                cells = [c.strip() for c in stripped.split('|')[1:-1]]
                
                if not in_examples:
                    headers = cells
                    in_examples = True
                else:
                    example_dict = {}
                    for j, header in enumerate(headers):
                        if j < len(cells):
                            example_dict[header] = cells[j]
                    if example_dict:
                        examples.append(example_dict)
        
        return examples if examples else None

    def extract_from_file(self, filepath, root_folder, rel_path):
        plain = self.parse_file(filepath)
        comps = []
        
        module_name = os.path.relpath(filepath, root_folder).replace("\\", "/")
        
        lines = plain.split('\n')
        current_line = 0
        
        # Feature block
        feature_match = re.search(r'^\s*Feature:\s*(.+)', plain, re.MULTILINE | re.IGNORECASE)
        
        if feature_match:
            feature_name = feature_match.group(1).strip()
            
            # Extract feature tags from first few lines
            feature_tags = None
            for line in lines[:10]:
                if line.strip().startswith('Feature:'):
                    break
                tags = self.extract_tags(line)
                if tags:
                    feature_tags = tags
                    break
            
            # Find feature description
            feature_desc_lines = []
            in_feature = False
            for line in lines:
                if line.strip().startswith('Feature:'):
                    in_feature = True
                    continue
                if in_feature and (line.strip().startswith('Background:') or 
                                   line.strip().startswith('Scenario:') or 
                                   line.strip().startswith('Scenario Outline:')):
                    break
                if in_feature and line.strip() and not line.strip().startswith('@'):
                    feature_desc_lines.append(line.strip())
            
            feature_description = ' '.join(feature_desc_lines) if feature_desc_lines else None
            
            comps.append({
                "kind": "feature",
                "module": module_name,
                "name": feature_name,
                "description": feature_description,
                "tags": feature_tags,
                "code": plain[:500],
                "start_line": 1,
                "end_line": len(lines),
            })
        
        # Parse Background, Scenario, Scenario Outline
        current_background = None
        background_steps = None
        
        for i, line in enumerate(lines):
            line_num = i + 1
            
            # Background
            bg_match = re.match(r'^\s*Background:\s*(.*)', line, re.IGNORECASE)
            if bg_match:
                bg_name = bg_match.group(1).strip() or "Background"
                bg_desc = bg_match.group(1).strip()
                
                # Get background steps
                bg_content = '\n'.join(lines[i:])
                bg_steps = self.extract_steps(bg_content, line_num)
                
                current_background = bg_name
                background_steps = bg_steps
                
                comps.append({
                    "kind": "background",
                    "module": module_name,
                    "name": bg_name,
                    "description": bg_desc if bg_desc else None,
                    "steps": bg_steps,
                    "code": '\n'.join(lines[i:i+20]),
                    "start_line": line_num,
                    "end_line": line_num + 20,
                })
                continue
            
            # Scenario Outline
            scenario_outline_match = re.match(r'^\s*Scenario Outline:\s*(.+)', line, re.IGNORECASE)
            if scenario_outline_match:
                scenario_name = scenario_outline_match.group(1).strip()
                
                # Get tags from previous lines
                tags = None
                for j in range(i-1, -1, -1):
                    if lines[j].strip().startswith('Scenario'):
                        break
                    tags = self.extract_tags(lines[j])
                    if tags:
                        break
                
                # Get scenario content until next scenario or end
                scenario_content = '\n'.join(lines[i:])
                
                # Extract examples table
                examples = self.extract_examples(scenario_content, line_num)
                
                # Get steps
                steps = self.extract_steps(scenario_content, line_num)
                
                comps.append({
                    "kind": "scenario_outline",
                    "module": module_name,
                    "name": scenario_name,
                    "tags": tags,
                    "steps": steps,
                    "examples": examples,
                    "uses_background": current_background is not None,
                    "background": current_background,
                    "code": '\n'.join(lines[i:i+30]),
                    "start_line": line_num,
                    "end_line": min(line_num + 30, len(lines)),
                })
                continue
            
            # Regular Scenario
            scenario_match = re.match(r'^\s*Scenario:\s*(.+)', line, re.IGNORECASE)
            if scenario_match:
                scenario_name = scenario_match.group(1).strip()
                
                # Get tags from previous lines
                tags = None
                for j in range(i-1, -1, -1):
                    if lines[j].strip().startswith('Scenario'):
                        break
                    tags = self.extract_tags(lines[j])
                    if tags:
                        break
                
                # Get scenario content
                scenario_content = '\n'.join(lines[i:])
                steps = self.extract_steps(scenario_content, line_num)
                
                comps.append({
                    "kind": "scenario",
                    "module": module_name,
                    "name": scenario_name,
                    "tags": tags,
                    "steps": steps,
                    "uses_background": current_background is not None,
                    "background": current_background,
                    "code": '\n'.join(lines[i:i+20]),
                    "start_line": line_num,
                    "end_line": line_num + 20,
                })
        
        return comps

    def extract_from_folder(self, folder):
        out = []
        project_root = os.environ.get("ROOT_DIR", "")
        abs_folder = os.path.abspath(folder)
        for root, _, files in os.walk(abs_folder):
            for f in files:
                if f.endswith('.feature'):
                    file_path = os.path.join(root, f)
                    rel = os.path.relpath(file_path, project_root).replace(os.sep, "/")
                    comps = self.extract_from_file(file_path, abs_folder, rel)
                    for c in comps:
                        c["file_path"] = rel
                        c.setdefault("module", rel)
                    out.extend(comps)
        return out

    def process_file(self, file_path: str):
        plain = self.parse_file(file_path)
        root_folder = os.path.dirname(file_path)
        
        project_root = os.environ.get("ROOT_DIR", "")
        rel = os.path.relpath(file_path, project_root).replace(os.sep, "/")
        
        raw = self.extract_from_file(file_path, root_folder, rel)
        
        # Add file_path to each component
        for c in raw:
            c["file_path"] = rel
            c.setdefault("module", rel)
        
        # Filter JSON-serializable
        self.all_components = [c for c in raw if self._is_jsonable(c)]

    def _is_jsonable(self, x):
        try:
            json.dumps(x)
            return True
        except Exception:
            return False

    def write_to_file(self, output_path: str):
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, "w", encoding="utf8") as f:
            json.dump(self.all_components, f, indent=2, ensure_ascii=False)

    def extract_all_components(self):
        return self.all_components
