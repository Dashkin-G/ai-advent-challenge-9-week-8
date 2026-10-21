"""Тесты app/support.py: формирование запросов к базе знаний и промпта для ответа поддержки."""
import unittest

from app import support


class SupportQueriesTest(unittest.TestCase):
    """Функция queries формирует запросы для поиска в базе знаний."""

    def test_queries_with_errors(self):
        """Запросы включают вопрос клиента и тексты ошибок из технических данных."""
        ticket = {'technical': {'body': {'error': 'валидация', 'details': 'body: ошибка'}}}
        result = support.queries('Почему 422?', ticket)
        self.assertEqual(result, ['Почему 422?', 'body: ошибка'])

    def test_queries_without_errors(self):
        """Без технических данных — только вопрос клиента."""
        result = support.queries('Как работает дашборд?', None)
        self.assertEqual(result, ['Как работает дашборд?'])

    def test_queries_deduplication(self):
        """Повторяющиеся ошибки идут один раз."""
        ticket = {'technical': {
            'body': {'details': 'ошибка'},
            'query': {'details': 'ошибка'}
        }}
        result = support.queries('Вопрос', ticket)
        self.assertEqual(result, ['Вопрос', 'ошибка'])


class SupportContextTextTest(unittest.TestCase):
    """Функция context_text формирует текст обращения для промпта."""

    def test_context_basic(self):
        """Базовый контекст с клиентом и обращением."""
        ticket = {'id': 'T-1041', 'subject': 'Ошибка', 'status': 'new', 'priority': 'high',
                  'created': '2026-10-21', 'message': 'Не работает', 'technical': {}}
        user = {'name': 'Иван', 'role': 'разработчик', 'org': 'Компания X',
                'channel': 'API', 'setup': 'Docker', 'notes': '', 'tickets': []}
        result = support.context_text(ticket, user)
        expected = ("Клиент: Иван — разработчик, Компания X. Работает с сервисом через API: Docker.\n"
                    "Обращение T-1041 «Ошибка» — new, приоритет high, 2026-10-21.\n"
                    "Сообщение клиента: Не работает")
        self.assertEqual(result, expected)

    def test_context_with_notes(self):
        """Заметки поддержки включаются в контекст."""
        ticket = {'id': 'T-1', 'subject': 'Q', 'status': 'new', 'priority': 'low',
                  'created': '2026-01-01', 'message': 'M', 'technical': {}}
        user = {'name': 'Анна', 'role': 'аналитик', 'org': 'Org Y',
                'channel': 'дашборд', 'setup': 'браузер', 'notes': 'Важный клиент', 'tickets': []}
        result = support.context_text(ticket, user)
        self.assertIn('Заметки поддержки: Важный клиент', result)

    def test_context_with_past_tickets(self):
        """Прошлые обращения перечисляются с результатами."""
        ticket = {'id': 'T-2', 'subject': 'Новое', 'status': 'open', 'priority': 'medium',
                  'created': '2026-10-22', 'message': 'Msg', 'technical': {}}
        user = {'name': 'Петр', 'role': 'user', 'org': 'Org',
                'channel': 'API', 'setup': 'curl', 'notes': '', 'tickets': [
                    {'id': 'T-1', 'subject': 'Старое', 'status': 'closed', 'resolution': 'fixed'}
                ]}
        result = support.context_text(ticket, user)
        self.assertIn('Прошлые обращения: T-1 «Старое» — closed: fixed', result)


class SupportMessagesTest(unittest.TestCase):
    """Функция messages формирует промпт для LLM."""

    def test_messages_structure(self):
        """Промпт содержит системную роль, данные CRM, фрагменты и вопрос."""
        hits = [{'file': 'README.md', 'title': 'Запуск', 'text': '# Запуск\nКоманда uvicorn'}]
        result = support.messages('Как запустить?', 'Контекст', hits)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]['role'], 'system')
        self.assertEqual(result[1]['role'], 'user')

    def test_messages_fragments(self):
        """Фрагменты форматированы как [файл › заголовок] текст."""
        hits = [{'file': 'docs/guide.md', 'title': 'API', 'text': 'Эндпоинт /api'}]
        messages = support.messages('Вопрос', None, hits)
        user_content = messages[1]['content']
        self.assertIn('[docs/guide.md › API]', user_content)
        self.assertIn('Эндпоинт /api', user_content)

    def test_messages_no_ticket(self):
        """Без обращения используется заглушка NO_TICKET."""
        result = support.messages('Вопрос', None, [])
        self.assertIn('Обращения нет:', result[1]['content'])


if __name__ == '__main__':
    unittest.main()
