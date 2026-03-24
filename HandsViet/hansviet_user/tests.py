import re

from django.test import TestCase, override_settings


@override_settings(ALLOWED_HOSTS=["testserver", "localhost", "127.0.0.1"])
class LanguageConsistencyTests(TestCase):
    def _get_home(self, lang=None):
        if lang:
            self.client.cookies["django_language"] = lang
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        return response.content.decode("utf-8", errors="ignore")

    def test_home_english_no_mixed_runtime_sentence(self):
        html = self._get_home(lang="en")
        self.assertIn("Home", html)
        self.assertIn("About", html)
        self.assertNotIn("English content is available.", html)

        mixed_fragments = (
            "committed hop",
            "team staff bac si specialist",
            "khach top tro nen khac biet",
            "Chung toi phat huy toi da the manh",
        )
        for fragment in mixed_fragments:
            self.assertNotIn(fragment, html)

    def test_home_vietnamese_switch_back(self):
        html = self._get_home(lang="vi")
        self.assertIn("Trang chủ", html)
        self.assertIn("Giới thiệu", html)
        self.assertNotIn("English content is available.", html)

        # Prevent mixed VI/EN artifacts in one sentence.
        mixed_sentence = re.compile(
            r"Chung toi|khach top|committed hop|team staff",
            re.IGNORECASE,
        )
        self.assertIsNone(mixed_sentence.search(html))
