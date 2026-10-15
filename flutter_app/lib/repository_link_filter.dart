/// Removes repository links from user-facing text and search evidence.
class RepositoryLinkFilter {
  static const Set<String> _repositoryHosts = <String>{
    'github.com',
    'githubusercontent.com',
    'github.io',
    'gitlab.com',
    'gitlab.io',
    'bitbucket.org',
    'sourceforge.net',
    'codeberg.org',
    'git.sr.ht',
    'huggingface.co',
  };

  static bool isRepositoryUrl(String rawUrl) {
    final cleaned = rawUrl.trim().replaceAll(RegExp(r'[),.;!?]+$'), '');
    var uri = Uri.tryParse(cleaned);
    if (uri == null || uri.host.isEmpty) {
      uri = Uri.tryParse('https://$cleaned');
    }
    final host = (uri?.host ?? '').toLowerCase().replaceFirst(RegExp(r'^www\.'), '');
    return _repositoryHosts.any((domain) => host == domain || host.endsWith('.$domain'));
  }

  /// Recursively sanitize server-provided values before any page renders them.
  /// This prevents repository URLs from leaking through signals, diagnostics,
  /// news evidence, strategy explanations, or future screens.
  static dynamic sanitizeValue(dynamic value) {
    if (value is String) return strip(value);
    if (value is List) {
      return value.map<dynamic>(sanitizeValue).toList(growable: false);
    }
    if (value is Map) {
      return value.map<dynamic, dynamic>(
        (key, item) => MapEntry<dynamic, dynamic>(key, sanitizeValue(item)),
      );
    }
    return value;
  }

  static String strip(String text) {
    var cleaned = text;
    // Keep a Markdown link's readable label while removing its repository target.
    cleaned = cleaned.replaceAllMapped(
      RegExp(r'\[([^\]]+)\]\((?:<)?(https?://[^)\s>]+)(?:>)?\)', caseSensitive: false),
      (match) => isRepositoryUrl(match.group(2)!) ? match.group(1)! : match.group(0)!,
    );
    cleaned = cleaned.replaceAllMapped(
      RegExp(r'<(https?://[^>\s]+)>', caseSensitive: false),
      (match) => isRepositoryUrl(match.group(1)!) ? '' : match.group(0)!,
    );
    cleaned = cleaned.replaceAllMapped(
      RegExp(r'https?://[^\s<>()]+', caseSensitive: false),
      (match) => isRepositoryUrl(match.group(0)!) ? '' : match.group(0)!,
    );
    cleaned = cleaned.replaceAll(
      RegExp(r'(?:www\.)?(?:github\.com|githubusercontent\.com|github\.io|gitlab\.com|gitlab\.io|bitbucket\.org|sourceforge\.net|codeberg\.org|git\.sr\.ht|huggingface\.co)/[^\s<>()\]]+', caseSensitive: false),
      '',
    );
    return cleaned
        .replaceAll(RegExp(r'[ \t]+\n'), '\n')
        .replaceAll(RegExp(r'\n{3,}'), '\n\n')
        .trim();
  }
}
