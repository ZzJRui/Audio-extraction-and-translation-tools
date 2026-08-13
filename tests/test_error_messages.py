import unittest

from app_service import build_error_message as build_service_error_message
from error_messages import parse_backend_error


class ErrorMessageTests(unittest.TestCase):
    def test_missing_llm_base_url_surfaces_readable_message(self) -> None:
        exc = ValueError("\u672a\u914d\u7f6e LLM_BASE_URL\uff0c\u8bf7\u5148\u5728 .env \u4e2d\u586b\u5199\u6a21\u578b\u63a5\u53e3\u5730\u5740\u3002")

        message, suggestion = build_service_error_message(exc)
        parsed_message, parsed_suggestion = parse_backend_error(f"ValueError:{exc}")

        self.assertEqual(message, f"\u5904\u7406\u5931\u8d25\uff1a{exc}")
        self.assertIsNone(suggestion)
        self.assertEqual(parsed_message, f"\u5904\u7406\u5931\u8d25\uff1a{exc}")
        self.assertIsNone(parsed_suggestion)

    def test_authentication_errors_keep_human_readable_guidance(self) -> None:
        message, suggestion = parse_backend_error("AuthenticationError: invalid api key")

        self.assertEqual(message, "\u5904\u7406\u5931\u8d25\uff1a\u7ffb\u8bd1\u63a5\u53e3\u8ba4\u8bc1\u5931\u8d25\u3002")
        self.assertEqual(suggestion, "\u5efa\u8bae\uff1a\u8bf7\u68c0\u67e5 .env \u91cc\u7684 LLM_API_KEY \u662f\u5426\u6b63\u786e\u3002")


if __name__ == "__main__":
    unittest.main()
