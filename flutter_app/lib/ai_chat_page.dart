import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';
import 'package:llama_flutter_android/llama_flutter_android.dart' as llama;
import 'package:shared_preferences/shared_preferences.dart';
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
  bool _localMode = false;
  bool _localLoaded = false;
  String? _localModelPath;
  llama.LlamaController? _localController;
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
    _localMode = false; // AI Chat is cloud-only; local model management lives in AI Access.
    _checkAiProvider();
    _restoreLocalModelPath();
  }

  Future<void> _restoreLocalModelPath() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final savedPaths = prefs.getStringList('fresh_local_qwen_model_paths') ?? <String>[];
      final legacyPath = prefs.getString('fresh_local_qwen_model_path');
      final paths = <String>{
        ...savedPaths.where((path) => path.trim().isNotEmpty),
        if (legacyPath != null && legacyPath.trim().isNotEmpty) legacyPath,
      }.toList();
      final selected = prefs.getString('fresh_local_qwen_selected_model_path') ?? legacyPath;
      if (mounted) {
        setState(() {
          _localModelPaths = paths;
          _localModelPath = selected != null && paths.contains(selected)
              ? selected
              : (paths.isNotEmpty ? paths.first : null);
        });
      }
    } catch (_) {
      // A moved or cleared model file is simply selected again by the user.
    }
  }

  Future<void> _sendLocal(String question, List<Map<String, String>> history) async {
    final controller = _localController;
    if (!_localLoaded || controller == null) {
      throw Exception('Local Qwen is not loaded. Choose the GGUF file and tap LOAD OFFLINE QWEN.');
    }
    Map<String, dynamic> engineContext = const {};
    try {
      engineContext = await FreshApi(widget.backendUrl).getJson(
        '/v1/ai/local-context?index=${Uri.encodeQueryComponent(_selectedIndex)}',
      );
    } catch (_) {
      // Offline chat remains available; explicitly tell the model context was unavailable.
      engineContext = const {'context_fetch_status': 'OFFLINE_OR_UNAVAILABLE'};
    }
    final contextText = jsonEncode(engineContext);
    final boundedContext = contextText.length > 14000
        ? '${contextText.substring(0, 14000)} [context truncated]'
        : contextText;
    final promptMessages = <llama.ChatMessage>[
      llama.ChatMessage(
        role: 'system',
        content: 'You are Fresh Local Qwen, running on this phone. You are an advisory validator, not an order engine. The JSON context below may include the APK/backend market snapshot, deterministic strategy, cloud AI decision, and Exa/Tavily evidence. Read it before answering. If context_fetch_status is OFFLINE_OR_UNAVAILABLE, or market_data_status is not LIVE_FRESH, explicitly say live context is unavailable/stale and do not issue actionable entries. Never invent prices, option strikes, entry, exit, stop-loss, target, P&L, source links, or dates. Cross-check proposed values against supplied quotes and flag missing/stale/conflicting fields. Output a concise verdict (PASS / WARN / REJECT), exact mismatches, missing data, and risk checks. Never promise zero mistakes or guaranteed profit. Deterministic engine, price freshness, and risk gates remain authoritative. Current engine context JSON: ' + boundedContext,
      ),
      ...history.map((message) => llama.ChatMessage(
        role: message['role']!,
        content: message['content']!,
      )),
      llama.ChatMessage(role: 'user', content: question),
    ];
    final answerIndex = _messages.length;
    setState(() => _messages.add({'role': 'assistant', 'content': ''}));
    final output = StringBuffer();
    final done = Completer<void>();
    controller.generateChat(
      messages: promptMessages,
      template: 'chatml',
      temperature: 0.35,
      maxTokens: 512,
    ).listen(
      (token) {
        output.write(token);
        if (mounted) {
          setState(() => _messages[answerIndex]['content'] = output.toString());
          _scrollToBottom();
        }
      },
      onError: (Object error, StackTrace stack) {
        if (!done.isCompleted) done.completeError(error, stack);
      },
      onDone: () {
        if (!done.isCompleted) done.complete();
      },
      cancelOnError: true,
    );
    await done.future;
    if (output.toString().trim().isEmpty) {
      throw Exception('Local model returned an empty answer.');
    }
    final validationRequest = RegExp(
      r'validate|validation|review engine|check (?:the )?(?:signal|trade|entry|exit)|stop.?loss|target|strike',
      caseSensitive: false,
    ).hasMatch(question);
    if (validationRequest) {
      try {
        await FreshApi(widget.backendUrl).postJson('/v1/ai/local-validation', {
          'index': _selectedIndex,
          'model_name': File(_localModelPath!).uri.pathSegments.last,
          'response': output.toString(),
          'context_market_data_status': (engineContext['market_data_status'] ?? 'UNKNOWN').toString(),
        });
      } catch (_) {
        // A local response must remain usable when the phone is offline.
      }
    }
    if (mounted) {
      setState(() {
        _aiProvider = 'local';
        _aiModel = File(_localModelPath!).uri.pathSegments.last;
        _providerStatus = 'OFFLINE';
      });
    }
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
    final controller = _localController;
    _localController = null;
    _localLoaded = false;
    // State.dispose is synchronous; make native cleanup errors visible in logs.
    if (controller != null) {
      controller.dispose().catchError((Object error, StackTrace stack) {
        debugPrint('FRESH_QWEN_DISPOSE_ERROR: $error');
      });
    }
    super.dispose();
  }

  Future<void> _send(String rawText) async {
    _localMode = false; // Cloud chat uses Gemini with configured provider failover; Qwen stays on-device.
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
      if (_localMode && _localLoaded) {
        try {
          await _sendLocal(question, history);
          return;
        } catch (localError) {
          // Remove the empty streaming placeholder created by a failed local inference.
          if (_messages.isNotEmpty &&
              _messages.last['role'] == 'assistant' &&
              (_messages.last['content'] ?? '').isEmpty) {
            _messages.removeLast();
          }
          if (!mounted) return;
          setState(() {
            _localLoaded = false;
            _localMode = false;
            _providerStatus = 'CLOUD FALLBACK • LOCAL INFERENCE FAILED';
            _error = 'Offline Qwen inference failed; switched to Cloud AI. Local error: ${localError.toString().replaceFirst('Exception: ', '')}';
          });
          // Continue through the normal cloud request below.
        }
      } else if (_localMode) {
        // The user selected local mode but no model is loaded; transparently use cloud.
        if (mounted) {
          setState(() {
            _localMode = false;
            _providerStatus = 'CLOUD FALLBACK • MODEL NOT LOADED';
            _error = 'Offline Qwen is not loaded. Using Cloud AI for this message.';
          });
        }
      }
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
          ? rawEvidence.whereType<Map>().toList(growable: false)
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
                const Text('Cloud AI + optional local offline Qwen • Market Q&A', textAlign: TextAlign.center, style: TextStyle(color: Color(0xFF32D583), fontWeight: FontWeight.w700, fontSize: 12)),
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
