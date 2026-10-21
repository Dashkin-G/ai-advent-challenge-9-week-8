"""Тесты app/assistant.py: парсинг команды /help и формирование промпта."""
import unittest

from app import assistant


class AssistantParseTest(unittest.TestCase):
    """Функция parse разбирает команду /help."""

    def test_parse_help_only(self):
        """Просто /help — общий вопрос о проекте."""
        result = assistant.parse('/help')
        self.assertEqual(result, 'Что это за проект, как он устроен и как его запустить?')

    def test_parse_help_with_question(self):
        """'/help вопрос' — только вопрос."""
        result = assistant.parse('/help Как запустить сервис?')
        self.assertEqual(result, 'Как запустить сервис?')

    def test_parse_without_help(self):
        """Без /help — None."""
        self.assertIsNone(assistant.parse('любой вопрос'))
        self.assertIsNone(assistant.parse(''))

    def test_parse_strips_whitespace(self):
        """Пробелы вокруг команды отбрасываются."""
        self.assertEqual(assistant.parse('  /help  '), 'Что это за проект, как он устроен и как его запустить?')
        self.assertEqual(assistant.parse('/help  Тест  '), 'Тест')


class AssistantReasonTest(unittest.TestCase):
    """Функция reason извлекает сообщение из ошибки."""

    def test_reason_simple_exception(self):
        """Обычное исключение — сообщение по str."""
        exc = Exception('ошибка подключения')
        self.assertEqual(assistant.reason(exc), 'ошибка подключения')

    def test_reason_with_message_attr(self):
        """Исключение с атрибутом message."""
        class CustomError(Exception):
            message = 'кастомная ошибка'
        exc = CustomError()
        self.assertEqual(assistant.reason(exc), 'кастомная ошибка')


class AssistantContextTextTest(unittest.TestCase):
    """Функция context_text форматирует результаты MCP для промпта."""

    def test_context_with_branch_and_files(self):
        """Контекст с веткой и списком файлов."""
        calls = [
            {'tool': 'git_branch', 'ok': True, 'result': {
                'branch': 'feature/x', 'branches': ['main', 'feature/x'], 'last_commit': 'abc123'
            }},
            {'tool': 'list_files', 'ok': True, 'result': {'count': 3, 'files': ['app/main.py', 'README.md', 'tests/test.py']}},
        ]
        result = assistant.context_text(calls)
        self.assertIn('Проект:', result)
        self.assertIn('Текущая ветка: feature/x', result)
        self.assertIn('Файлы проекта (3)', result)

    def test_context_clean_status(self):
        """Чистое рабочее дерево без изменений."""
        calls = [
            {'tool': 'git_branch', 'ok': True, 'result': {'branch': 'main', 'branches': ['main'], 'last_commit': 'def456'}},
            {'tool': 'git_status', 'ok': True, 'result': {'clean': True, 'count': 0, 'changed': []}},
        ]
        result = assistant.context_text(calls)
        self.assertIn('Незакоммиченных изменений нет', result)

    def test_context_changed_files(self):
        """Изменённые файлы группируются по статусу."""
        calls = [
            {'tool': 'git_status', 'ok': True, 'result': {
                'clean': False, 'count': 3, 'changed': [
                    {'status': 'изменён', 'path': 'app/main.py'},
                    {'status': 'новый', 'path': 'tests/new.py'},
                    {'status': 'удалён', 'path': 'old.py'}
                ]
            }},
        ]
        result = assistant.context_text(calls)
        self.assertIn('изменены', result)
        self.assertIn('новые', result)
        self.assertIn('удалены', result)


class AssistantMessagesTest(unittest.TestCase):
    """Функция messages формирует промпт для LLM."""

    def test_messages_structure(self):
        """Промпт содержит системный ролевик и пользовательский запрос."""
        hits = [{'file': 'README.md', 'title': 'Введение', 'text': 'Краткое описание'}]
        result = assistant.messages('Вопрос?', 'Контекст git', hits)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]['role'], 'system')
        self.assertEqual(result[1]['role'], 'user')

    def test_messages_with_fragments(self):
        """Фрагменты вставляются между контекстом и вопросом."""
        hits = [{'file': 'docs/api.md', 'title': 'Эндпоинты', 'text': '/api/help'}]
        messages = assistant.messages('Как помочь?', 'Git info', hits)
        user_content = messages[1]['content']
        self.assertIn('Контекст проекта', user_content)
        self.assertIn('[docs/api.md › Эндпоинты]', user_content)
        self.assertIn('/api/help', user_content)


if __name__ == '__main__':
    unittest.main()
