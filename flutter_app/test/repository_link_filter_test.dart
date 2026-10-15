import 'package:flutter_test/flutter_test.dart';
import 'package:ai_trading_signal/repository_link_filter.dart';

void main() {
  group('RepositoryLinkFilter.isRepositoryUrl', () {
    test('recognizes repository hosting URLs and subdomains', () {
      expect(RepositoryLinkFilter.isRepositoryUrl('https://github.com/org/repo'), isTrue);
      expect(RepositoryLinkFilter.isRepositoryUrl('https://www.gitlab.com/org/repo'), isTrue);
      expect(RepositoryLinkFilter.isRepositoryUrl('https://raw.githubusercontent.com/org/repo/main/a.dart'), isTrue);
      expect(RepositoryLinkFilter.isRepositoryUrl('https://huggingface.co/org/model'), isTrue);
      expect(RepositoryLinkFilter.isRepositoryUrl('https://example.com/article'), isFalse);
    });
  });

  group('RepositoryLinkFilter.strip', () {
    test('keeps a Markdown label but removes its repository target', () {
      expect(
        RepositoryLinkFilter.strip('Read [the source](https://github.com/org/repo) now.'),
        'Read the source now.',
      );
    });

    test('removes bare and scheme-less repository URLs', () {
      expect(
        RepositoryLinkFilter.strip('Code: https://github.com/org/repo and gitlab.com/org/project'),
        'Code:  and',
      );
    });

    test('preserves normal source URLs', () {
      expect(
        RepositoryLinkFilter.strip('Read https://example.com/market-news'),
        'Read https://example.com/market-news',
      );
    });
  });
}
