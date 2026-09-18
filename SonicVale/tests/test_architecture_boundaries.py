import ast
from pathlib import Path
import unittest

class ArchitectureBoundariesTest(unittest.TestCase):
    def test_runtime_and_assembly_do_not_import_http(self):
        app=Path(__file__).parents[1]/'app'
        for path in [app/'services/factory.py',app/'core/tts_runtime.py',*list((app/'runtime').glob('*.py'))]:
            for node in ast.walk(ast.parse(path.read_text())):
                if isinstance(node,ast.ImportFrom):
                    self.assertFalse((node.module or '').startswith('app.routers'),str(path))

    def test_adapters_cannot_import_orm_or_business_services(self):
        app=Path(__file__).parents[1]/'app'
        for path in (app/'integrations').rglob('*.py'):
            for node in ast.walk(ast.parse(path.read_text())):
                if isinstance(node,ast.ImportFrom):
                    self.assertFalse((node.module or '').startswith(('sqlalchemy','app.models','app.repositories','app.services','app.routers')),str(path))

    def test_main_has_no_router_service_import(self):
        source=(Path(__file__).parents[1]/'app/main.py').read_text()
        for node in ast.walk(ast.parse(source)):
            if isinstance(node,ast.ImportFrom) and (node.module or '').startswith('app.routers.'):
                self.assertFalse(any(name.name.startswith('get_') for name in node.names))
