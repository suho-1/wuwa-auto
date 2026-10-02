"""Report which template features the code expects but nobody annotated yet.

Usage:
    python training/check_annotations.py

It cross-checks three things:

1. every ``Labels.*`` constant against the categories in
   ``assets/coco_annotations.json`` (a missing category means the feature can
   never be found at runtime);
2. every character registered in ``src/char/CharFactory.py`` (a missing avatar
   template means that character is simply never recognized in the team);
3. every literal feature name passed to ``find_one`` / ``wait_feature`` /
   ``get_box_by_name`` & friends in ``src/``.

Annotate the reported names with the Annotation Studio (``src/gui``) on a
screenshot placed in ``assets/images``.
"""

import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
COCO = os.path.join(ROOT, 'assets', 'coco_annotations.json')

FEATURE_CALLS = re.compile(
    r"(find_one|find_feature|wait_feature|wait_click_feature|find_best_match_in_box"
    r"|wait_until_feature|find_feature_and_set|get_box_by_name)\s*\(")
STRING = re.compile(r"['\"]([a-zA-Z0-9_]{3,})['\"]")
# names resolved by ok.BaseTask.get_box_by_name without an annotation
BUILTIN_BOXES = {'full_screen', 'left', 'right', 'top', 'bottom', 'top_left',
                 'top_right', 'bottom_left', 'bottom_right'}


def annotated_categories():
    with open(COCO, encoding='utf-8') as f:
        data = json.load(f)
    return {c['name'] for c in data['categories']}


def label_constants():
    text = open(os.path.join(ROOT, 'src', 'Labels.py'), encoding='utf-8').read()
    return dict(re.findall(r"^\s{4}([A-Za-z0-9_]+)\s*=\s*'([^']+)'", text, re.M))


def character_templates(labels):
    text = open(os.path.join(ROOT, 'src', 'char', 'CharFactory.py'), encoding='utf-8').read()
    raw = text.split('_char_dict_raw')[1] if '_char_dict_raw' in text else text
    return [labels.get(name, name) for name in dict.fromkeys(re.findall(r"Labels\.([A-Za-z0-9_]+)", raw))]


def referenced_features():
    found = {}
    for folder, _, files in os.walk(os.path.join(ROOT, 'src')):
        if '__pycache__' in folder:
            continue
        for file_name in files:
            if not file_name.endswith('.py'):
                continue
            path = os.path.join(folder, file_name)
            text = open(path, encoding='utf-8').read()
            for match in FEATURE_CALLS.finditer(text):
                index, depth = match.end(), 1
                while index < len(text) and depth:
                    if text[index] == '(':
                        depth += 1
                    elif text[index] == ')':
                        depth -= 1
                    index += 1
                for name in STRING.findall(text[match.end():index]):
                    found.setdefault(name, set()).add(os.path.relpath(path, ROOT))
    return found


def main():
    categories = annotated_categories()
    labels = label_constants()

    missing_labels = sorted(v for v in set(labels.values()) if v not in categories)
    missing_chars = [v for v in character_templates(labels) if v not in categories]
    referenced = referenced_features()
    missing_refs = {k: v for k, v in referenced.items()
                    if k not in categories and k not in BUILTIN_BOXES and k not in labels.values()}

    print(f'annotated categories: {len(categories)}')

    print(f'\nLabels.* without an annotated feature ({len(missing_labels)}):')
    for name in missing_labels:
        print(f'  - {name}')

    print(f'\ncharacters registered in CharFactory without an avatar template ({len(missing_chars)}):')
    for name in missing_chars:
        print(f'  - {name}')

    print(f'\nother feature names used in code but not annotated ({len(missing_refs)}):')
    for name, files in sorted(missing_refs.items()):
        print(f'  - {name}  ({", ".join(sorted(files))})')

    return 1 if (missing_labels or missing_chars or missing_refs) else 0


if __name__ == '__main__':
    sys.exit(main())
