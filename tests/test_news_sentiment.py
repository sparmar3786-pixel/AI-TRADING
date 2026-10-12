"""Unit tests for conservative, dependency-free headline scoring."""
import unittest

from integrations.news_sentiment import score_news_articles


class NewsSentimentTests(unittest.TestCase):
    def test_bullish_headlines_score_positive(self):
        result = score_news_articles([
            {"title": "Nifty rally gains as strong buying interest returns"},
            {"title": "Banking stocks surge on upbeat outlook"},
        ])
        self.assertEqual(result["status"], "LIVE_EVIDENCE")
        self.assertEqual(result["label"], "BULLISH")
        self.assertGreater(result["score"], 0)

    def test_bearish_headlines_score_negative(self):
        result = score_news_articles([
            {"title": "Markets fall as selloff and outflow pressure grows"},
            {"title": "Banking stocks decline on weak outlook"},
        ])
        self.assertEqual(result["label"], "BEARISH")
        self.assertLess(result["score"], 0)

    def test_empty_headlines_never_invent_sentiment(self):
        result = score_news_articles([])
        self.assertEqual(result["status"], "NO_EVIDENCE")
        self.assertEqual(result["label"], "UNKNOWN")
        self.assertIsNone(result["score"])


if __name__ == "__main__":
    unittest.main()
