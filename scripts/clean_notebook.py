"""Clear local notebook outputs before committing; preserve source and cell IDs."""
import json
from pathlib import Path

path = Path(__file__).resolve().parents[1] / 'ARIN7101_Context_Bandit_Release_Notebook.ipynb'
document = json.loads(path.read_text(encoding='utf-8'))
for cell in document['cells']:
    if cell['cell_type'] == 'code':
        cell['outputs'] = []
        cell['execution_count'] = None
    for key in ['execution', 'ExecuteTime', 'collapsed', 'scrolled']:
        cell['metadata'].pop(key, None)
document['metadata'].pop('widgets', None)
path.write_text(json.dumps(document, ensure_ascii=False, indent=1)+'\n', encoding='utf-8')
print('Cleared outputs:', path.name)
