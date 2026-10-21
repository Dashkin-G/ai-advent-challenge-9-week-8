"""Тесты app/rag.py: нарезка документации и кода на фрагменты для RAG."""
import unittest

from app import rag


class RagSplitDocsTest(unittest.TestCase):
    """Функция split_docs разбивает Markdown на фрагменты по заголовкам."""

    def test_split_simple(self):
        """Простой документ с одним разделом."""
        text = "# README\n\n## Запуск\n\nКоманда uvicorn"
        chunks = list(rag.split_docs('README.md', text))
        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0]['file'], 'README.md')
        self.assertEqual(chunks[0]['title'], 'Запуск')
        self.assertEqual(chunks[0]['text'], 'Команда uvicorn')
        self.assertEqual(chunks[0]['kind'], 'docs')

    def test_split_nested_headings(self):
        """Вложенные заголовки формируют составной заголовок фрагмента."""
        text = "# README\n\n## Руководство\n\n### Установка\n\npip install pkg"
        chunks = list(rag.split_docs('README.md', text))
        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0]['title'], 'Руководство › Установка')
        self.assertEqual(chunks[0]['text'], 'pip install pkg')

    def test_split_code_blocks(self):
        """Блоки кода не обрабатываются как заголовки."""
        text = """# README

## Пример

```python
def hello():
    pass
```
"""
        chunks = list(rag.split_docs('README.md', text))
        self.assertEqual(len(chunks), 1)
        self.assertIn('def hello():', chunks[0]['text'])


class RagSplitCodeTest(unittest.TestCase):
    """Функция split_code разбивает Python на фрагменты по функциям и классам."""

    def test_split_function(self):
        """Функция идёт целиком с номерами строк."""
        text = "def hello():\n    print('hello')"
        chunks = list(rag.split_code('app/test.py', text))
        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0]['title'], 'hello()')
        self.assertEqual(chunks[0]['lines'], [1, 2])
        self.assertEqual(chunks[0]['kind'], 'code')

    def test_split_class(self):
        """Класс идёт целиком."""
        text = "class Test:\n    pass"
        chunks = list(rag.split_code('app/test.py', text))
        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0]['title'], 'class Test')
        self.assertEqual(chunks[0]['lines'], [1, 2])

    def test_split_multiple_functions(self):
        """Несколько функций — отдельные фрагменты."""
        text = "def a():\n    pass\n\ndef b():\n    return True"
        chunks = list(rag.split_code('app/test.py', text))
        self.assertEqual(len(chunks), 2)
        self.assertEqual(chunks[0]['title'], 'a()')
        self.assertEqual(chunks[1]['title'], 'b()')


class RagSourceTest(unittest.TestCase):
    """Функция source форматирует ссылку на фрагмент."""

    def test_source_docs(self):
        """Документация без номеров строк."""
        chunk = {'file': 'README.md', 'title': 'Запуск', 'kind': 'docs'}
        self.assertEqual(rag.source(chunk), 'README.md › Запуск')

    def test_source_code_with_lines(self):
        """Код с номерами строк."""
        chunk = {'file': 'app/main.py', 'title': 'answer()', 'kind': 'code', 'lines': [10, 25]}
        self.assertEqual(rag.source(chunk), 'app/main.py › answer(), строки 10–25')


class RagSplitTest(unittest.TestCase):
    """Функция split выбирает режим по расширению файла."""

    def test_split_py_uses_code(self):
        """Python файлы разбиваются через split_code."""
        text = "def f():\n    pass"
        chunks = list(rag.split('app/test.py', text))
        self.assertEqual(chunks[0]['kind'], 'code')

    def test_split_md_uses_docs(self):
        """Markdown файлы разбиваются через split_docs."""
        text = "# Title\n\nText"
        chunks = list(rag.split('README.md', text))
        self.assertEqual(chunks[0]['kind'], 'docs')


if __name__ == '__main__':
    unittest.main()
