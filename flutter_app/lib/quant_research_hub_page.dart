import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';

class QuantResearchHubPage extends StatelessWidget {
  const QuantResearchHubPage({super.key});

  static const _resources = <_ResearchResource>[
    _ResearchResource(
      title: 'Awesome Systematic Trading',
      owner: 'paperswithbacktest',
      url: 'https://github.com/paperswithbacktest/awesome-systematic-trading',
      description: 'Curated systematic-trading libraries, strategy papers with replication records, books, videos, blogs and courses.',
      tags: ['Strategies', 'Backtesting', 'Libraries', 'Books'],
      icon: Icons.track_changes,
    ),
    _ResearchResource(
      title: 'Awesome Algorithmic Trading',
      owner: 'joelowj',
      url: 'https://github.com/joelowj/awesome-algorithmic-trading',
      description: 'Learning resources for market mechanics, price data, momentum, volatility, mean reversion, portfolio risk and factor models.',
      tags: ['Market data', 'Momentum', 'Risk', 'Factors'],
      icon: Icons.auto_graph,
    ),
    _ResearchResource(
      title: 'Awesome Quant',
      owner: 'wilsonfreitas',
      url: 'https://github.com/wilsonfreitas/awesome-quant',
      description: 'A broad quantitative-finance resource index spanning analytics, data handling, portfolio methods and quantitative research tools.',
      tags: ['Quant finance', 'Analytics', 'Portfolio', 'Tools'],
      icon: Icons.functions,
    ),
    _ResearchResource(
      title: 'Awesome Deep Trading',
      owner: 'cbailes',
      url: 'https://github.com/cbailes/awesome-deep-trading',
      description: 'Research papers and projects on deep learning for trading, including CNNs, LSTMs, GANs, reinforcement learning, portfolio work and sentiment.',
      tags: ['Deep learning', 'Reinforcement learning', 'Papers', 'Sentiment'],
      icon: Icons.psychology_alt,
    ),
    _ResearchResource(
      title: 'Stock Market Dashboard',
      owner: 'vikram-2101',
      url: 'https://github.com/vikram-2101/Stock-Market-Dashboard',
      description: 'React dashboard reference covering market overview, index moves, interactive charts, company details and top movers.',
      tags: ['Dashboard UI', 'Charts', 'Market overview', 'Top movers'],
      icon: Icons.dashboard_customize,
    ),
    _ResearchResource(
      title: 'AI Stock Market Dashboard',
      owner: 'DevMLAI01',
      url: 'https://github.com/DevMLAI01/stock-market-dashboard',
      description: 'Indian-stock research reference with a natural-language screener, watchlists, filter history, fundamentals and candlestick charts.',
      tags: ['AI screener', 'Watchlists', 'Fundamentals', 'NSE'],
      icon: Icons.manage_search,
    ),
  ];

  Future<void> _open(String url) async {
    final uri = Uri.parse(url);
    await launchUrl(uri, mode: LaunchMode.externalApplication);
  }

  @override
  Widget build(BuildContext context) => ListView(
        padding: const EdgeInsets.all(12),
        children: [
          const Text(
            'QUANT RESEARCH HUB',
            style: TextStyle(fontWeight: FontWeight.w900, letterSpacing: 1.1, fontSize: 18),
          ),
          const SizedBox(height: 6),
          const Text(
            'A curated in-app index of the six requested public repositories. Open a source to explore its full README, papers, projects and licenses.',
            style: TextStyle(color: Colors.white70, fontSize: 12),
          ),
          const SizedBox(height: 12),
          Card(
            child: Padding(
              padding: const EdgeInsets.all(14),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: const [
                  Text('RESEARCH WORKFLOW', style: TextStyle(fontWeight: FontWeight.w900)),
                  SizedBox(height: 8),
                  _WorkflowRow(icon: Icons.search, title: '1. Discover', detail: 'Find a strategy or research paper in the linked libraries.'),
                  _WorkflowRow(icon: Icons.science_outlined, title: '2. Validate', detail: 'Check data requirements, transaction costs, look-ahead bias and out-of-sample performance.'),
                  _WorkflowRow(icon: Icons.query_stats, title: '3. Backtest', detail: 'Use the Backtesting tab for the app’s supported historical index-candle replay.'),
                  _WorkflowRow(icon: Icons.verified_outlined, title: '4. Review', detail: 'Treat results as research, not a promise of future returns or a live trade instruction.'),
                ],
              ),
            ),
          ),
          const SizedBox(height: 8),
          for (final resource in _resources)
            Card(
              child: Padding(
                padding: const EdgeInsets.all(12),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Container(
                          width: 42,
                          height: 42,
                          decoration: BoxDecoration(
                            color: const Color(0xFF12D6FF).withValues(alpha: 0.12),
                            borderRadius: BorderRadius.circular(12),
                          ),
                          child: Icon(resource.icon, color: const Color(0xFF12D6FF)),
                        ),
                        const SizedBox(width: 10),
                        Expanded(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text(resource.title, style: const TextStyle(fontWeight: FontWeight.w800)),
                              Text('@${resource.owner}', style: const TextStyle(color: Colors.white60, fontSize: 11)),
                            ],
                          ),
                        ),
                        IconButton(
                          tooltip: 'Open GitHub repository',
                          onPressed: () => _open(resource.url),
                          icon: const Icon(Icons.open_in_new, color: Color(0xFF12D6FF)),
                        ),
                      ],
                    ),
                    const SizedBox(height: 8),
                    Text(resource.description, style: const TextStyle(fontSize: 12, color: Colors.white70)),
                    const SizedBox(height: 9),
                    Wrap(
                      spacing: 6,
                      runSpacing: 6,
                      children: resource.tags
                          .map((tag) => Chip(
                                label: Text(tag, style: const TextStyle(fontSize: 10)),
                                visualDensity: VisualDensity.compact,
                                side: BorderSide(color: Colors.white.withValues(alpha: 0.12)),
                              ))
                          .toList(),
                    ),
                    Align(
                      alignment: Alignment.centerRight,
                      child: TextButton.icon(
                        onPressed: () => _open(resource.url),
                        icon: const Icon(Icons.open_in_new, size: 16),
                        label: const Text('View source'),
                      ),
                    ),
                  ],
                ),
              ),
            ),
          const SizedBox(height: 8),
          const Card(
            child: Padding(
              padding: EdgeInsets.all(12),
              child: Text(
                'Source and licensing note: this tab summarizes repository topics and links to the originals; it does not bundle their entire codebases or imply endorsement. Review each repository’s license before reusing code. External repositories are reference material, not live market-data providers.',
                style: TextStyle(fontSize: 11, color: Colors.white70),
              ),
            ),
          ),
        ],
      );
}

class _ResearchResource {
  const _ResearchResource({
    required this.title,
    required this.owner,
    required this.url,
    required this.description,
    required this.tags,
    required this.icon,
  });

  final String title;
  final String owner;
  final String url;
  final String description;
  final List<String> tags;
  final IconData icon;
}

class _WorkflowRow extends StatelessWidget {
  const _WorkflowRow({required this.icon, required this.title, required this.detail});

  final IconData icon;
  final String title;
  final String detail;

  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.only(bottom: 9),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Icon(icon, size: 19, color: const Color(0xFF12D6FF)),
            const SizedBox(width: 9),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(title, style: const TextStyle(fontWeight: FontWeight.w700)),
                  Text(detail, style: const TextStyle(fontSize: 11, color: Colors.white70)),
                ],
              ),
            ),
          ],
        ),
      );
}
