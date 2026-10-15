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

    test('recursively removes repository links from nested API payloads', () {
      final result = RepositoryLinkFilter.sanitizeValue(<String, dynamic>{
        'answer': 'Read https://github.com/org/repo',
        'evidence': [
          <String, dynamic>{
            'title': 'Useful article',
            'url': 'https://gitlab.com/org/project',
            'nested': <String, dynamic>{
              'description': 'See https://example.com/article and https://github.com/org/repo',
            },
          },
        ],
      }) as Map;
      expect(result['answer'], 'Read');
      final evidence = result['evidence'] as List;
      final item = evidence.single as Map;
      expect(item['title'], 'Useful article');
      expect(item['url'], '');
      expect(item['nested']['description'], 'See https://example.com/article and');
    });

    test('preserves normal source URLs', () {
      expect(
        RepositoryLinkFilter.strip('Read https://example.com/market-news'),
        'Read https://example.com/market-news',
      );
    });
  });
}
