import 'package:flutter/material.dart';
import 'package:stream_chat_flutter_ai/stream_chat_flutter_ai.dart';
import 'api.dart';

class AiChatPage extends StatefulWidget {
  const AiChatPage({required this.backendUrl, required this.selectedIndex, super.key});

  final String backendUrl;
  final String selectedIndex;

  @override
  State<AiChatPage> createState() => _AiChatPageState();
}

class _AiChatPageState extends State<AiChatPage> {
  final ChatComposerController _composerController = ChatComposerController();
  final ScrollController _scrollController = ScrollController();
  final List<Map<String, String>> _messages = [];
  bool _busy = false;
  String _aiProvider = 'unknown';
  String _aiModel = 'unknown';
  String _providerStatus = 'not checked';
  String? _error;
  String _selectedIndex = 'NIFTY';

  static const _suggestions = [
    'Validate current engine signal, entry, exit, stop-loss, target and strike against the supplied live data. Return PASS, WARN or REJECT and explain every missing field.',
    'NIFTY ka current market context samjhao',
    'Current signal aur uske risk explain karo',
    'Aaj ke market data mein kya missing hai?',
  ];

  @override
  void initState() {
    super.initState();
    _selectedIndex = widget.selectedIndex;
    _checkAiProvider();
  }

  Future<void> _checkAiProvider() async {
    try {
      final status = await FreshApi(widget.backendUrl).getJson('/v1/ai/status');
      if (!mounted) return;
      setState(() {
        _aiProvider = (status['provider'] ?? 'unknown').toString();
        _aiModel = (status['model'] ?? 'unknown').toString();
        _providerStatus = (status['status'] ?? 'unknown').toString();
      });
    } catch (_) {
      if (!mounted) return;
      setState(() => _providerStatus = 'status unavailable');
    }
  }

  @override
  void didUpdateWidget(covariant AiChatPage oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.selectedIndex != widget.selectedIndex) {
      _selectedIndex = widget.selectedIndex;
    }
  }

  @override
  void dispose() {
    _composerController.dispose();
    _scrollController.dispose();
    super.dispose();
  }

  Future<void> _send(String rawText) async {
    final question = rawText.trim();
    if (question.isEmpty || _busy) return;
    final history = _messages.map((message) => {
      'role': message['role']!,
      'content': message['content']!,
    }).toList(growable: false);

    setState(() {
      _busy = true;
      _error = null;
      _messages.add({'role': 'user', 'content': question});
    });
    _scrollToBottom();

    try {
      final response = await FreshApi(widget.backendUrl).aiChat(
        index: _selectedIndex,
        question: question,
        history: history,
      );
      final answer = (response['answer'] ?? '').toString().trim();
      if (answer.isEmpty) throw Exception('AI returned an empty answer.');

      // Show server-confirmed evidence in the chat itself instead of relying
      // only on the model to remember to print citations in its prose.
      var displayAnswer = answer;
      final rawEvidence = response['search_evidence'];
      final evidence = rawEvidence is List
          ? rawEvidence.whereType<Map>().where((source) { final rawUrl = (source['url'] ?? source['source_url'] ?? source['link'] ?? '').toString().trim().toLowerCase(); final uri = Uri.tryParse(rawUrl); final host = uri?.host ?? ''; return !<String>{'github.com', 'www.github.com', 'raw.githubusercontent.com', 'gitlab.com', 'www.gitlab.com', 'bitbucket.org', 'www.bitbucket.org', 'sourceforge.net', 'www.sourceforge.net'}.contains(host); }).toList(growable: false)
          : <Map>[];
      if (evidence.isNotEmpty) {
        final sourceLines = <String>[];
        for (final source in evidence) {
          final title = (source['title'] ?? 'Untitled source').toString();
          final provider = (source['provider'] ?? 'search').toString();
          final url = (source['url'] ?? '').toString();
          final published = (source['published_at'] ?? '').toString();
          sourceLines.add('- **$title** ($provider)${published.isNotEmpty ? ' • $published' : ''}${url.isNotEmpty ? '\n  $url' : ''}');
        }
        displayAnswer += '\n\n**Live Search Evidence — ${evidence.length} source(s)**\n${sourceLines.join('\n')}';
      } else if (response['search_attempted'] == true) {
        displayAnswer += '\n\n**Live Search Evidence:** Exa/Tavily search was attempted, but this request returned no source results.';
      } else {
        displayAnswer += '\n\n**Live Search Evidence:** Search providers are not configured for this chat request.';
      }
      if (!mounted) return;
      setState(() {
        _aiProvider = (response['provider'] ?? _aiProvider).toString();
        _aiModel = (response['model'] ?? _aiModel).toString();
        _providerStatus = 'CONNECTED';
        _messages.add({'role': 'assistant', 'content': displayAnswer});
      });
      _scrollToBottom();
    } catch (e) {
      if (!mounted) return;
      final errorText = e.toString().replaceFirst('Exception: ', '');
      setState(() {
        _providerStatus = errorText.toLowerCase().contains('recovery cooldown')
            ? 'COOLDOWN'
            : 'ERROR';
        _error = errorText;
      });
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  void _scrollToBottom() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (_scrollController.hasClients) {
        _scrollController.animateTo(
          _scrollController.position.maxScrollExtent,
          duration: const Duration(milliseconds: 250),
          curve: Curves.easeOut,
        );
      }
    });
  }

  @override
  Widget build(BuildContext context) => Column(
    children: [
      Container(
        width: double.infinity,
        padding: const EdgeInsets.fromLTRB(16, 14, 16, 12),
        decoration: BoxDecoration(
          color: Theme.of(context).colorScheme.surfaceContainerHighest.withValues(alpha: 0.35),
          border: Border(bottom: BorderSide(color: Theme.of(context).dividerColor.withValues(alpha: 0.35))),
        ),
        child: Wrap(
          crossAxisAlignment: WrapCrossAlignment.center,
          spacing: 10,
          runSpacing: 8,
          children: [
            const Icon(Icons.auto_awesome, color: Color(0xFF12D6FF)),
            const Text('AI MARKET CHAT', style: TextStyle(fontWeight: FontWeight.w900, letterSpacing: 1)),
            const Chip(avatar: Icon(Icons.cloud_done, size: 16, color: Color(0xFF32D583)), label: Text('CLOUD AI • AUTO FAILOVER')),
            Text('Provider: $_aiProvider • Model: $_aiModel • $_providerStatus', style: const TextStyle(fontSize: 10, color: Colors.white60)),
          ],
        ),
      ),
      Expanded(
        child: _messages.isEmpty
          ? ListView(
              padding: const EdgeInsets.all(18),
              children: [
                const SizedBox(height: 18),
                const Icon(Icons.psychology_alt, size: 54, color: Color(0xFF12D6FF)),
                const SizedBox(height: 12),
                const Text('Ask Fresh AI', textAlign: TextAlign.center, style: TextStyle(fontSize: 22, fontWeight: FontWeight.w900)),
                const SizedBox(height: 6),
                const Text('Cloud AI • Market Q&A', textAlign: TextAlign.center, style: TextStyle(color: Color(0xFF32D583), fontWeight: FontWeight.w700, fontSize: 12)),
                const SizedBox(height: 8),
                const Text(
                  'Load a local GGUF model for offline inference. When the backend is reachable, local Qwen receives the selected index snapshot, deterministic strategy, cloud AI status and search evidence. Without backend access it must report that live context is unavailable.',
                  textAlign: TextAlign.center,
                ),
                const SizedBox(height: 20),
                AISuggestionsView(
                  suggestions: _suggestions,
                  onSuggestionSelected: (text) => _send(text),
                ),
              ],
            )
          : ListView.builder(
              controller: _scrollController,
              padding: const EdgeInsets.all(12),
              itemCount: _messages.length + (_busy ? 1 : 0),
              itemBuilder: (context, index) {
                if (_busy && index == _messages.length) {
                  return const Padding(
                    padding: EdgeInsets.all(12),
                    child: Row(children: [
                      SizedBox(width: 16, height: 16, child: CircularProgressIndicator(strokeWidth: 2)),
                      SizedBox(width: 10),
                      AITypingIndicatorView(text: 'Thinking'),
                    ]),
                  );
                }
                final message = _messages[index];
                final isUser = message['role'] == 'user';
                return Align(
                  alignment: isUser ? Alignment.centerRight : Alignment.centerLeft,
                  child: Container(
                    constraints: const BoxConstraints(maxWidth: 760),
                    margin: const EdgeInsets.symmetric(vertical: 6),
                    padding: const EdgeInsets.all(12),
                    decoration: BoxDecoration(
                      color: isUser
                        ? const Color(0xFF123B52)
                        : Theme.of(context).colorScheme.surfaceContainerHighest.withValues(alpha: 0.65),
                      borderRadius: BorderRadius.circular(14),
                    ),
                    child: isUser
                      ? SelectableText(message['content']!)
                      : StreamingMessageView(
                          text: message['content']!,
                          typingSpeed: const Duration(milliseconds: 8),
                        ),
                  ),
                );
              },
            ),
      ),
      if (_error != null)
        Container(
          width: double.infinity,
          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
          color: Theme.of(context).colorScheme.errorContainer,
          child: Text('AI error: $_error', style: TextStyle(color: Theme.of(context).colorScheme.onErrorContainer)),
        ),
      if (_busy)
        const LinearProgressIndicator(minHeight: 2),
      SafeArea(
        top: false,
        child: Padding(
          padding: const EdgeInsets.fromLTRB(10, 8, 10, 10),
          child: ChatComposer(
            controller: _composerController,
            onSendPressed: (text, selectedOption, attachments) {
              if (attachments.isNotEmpty && mounted) {
                setState(() => _error = 'Attachments are not enabled for this backend chat yet. Send text only.');
              }
              _send(text);
            },
          ),
        ),
      ),
    ],
  );
}
