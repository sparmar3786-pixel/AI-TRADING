"""
Multi-Source Data Fetcher
==========================
Aggregates data from multiple free APIs for comprehensive market analysis.

Data Sources:
1. Tiingo - EOD prices, intraday, news (user's existing key)
2. Finnhub - Company profile, real-time quotes, news, insider sentiment
3. FMP (Financial Modeling Prep) - Float, shares outstanding, fundamentals
4. Alpha Vantage - News sentiment, company overview

Free Tier Limits:
- Tiingo: 1000 requests/day (free tier)
- Finnhub: 60 requests/minute
- FMP: 250 requests/day
- Alpha Vantage: 25 requests/day

For runner detection we need:
- Float shares (low float = squeeze potential)
- Short interest (high = squeeze potential)
- Volume vs average (explosion = attention)
- Pre-market data (gap up = momentum)
- News/catalysts (reason for move)
- Price breakout (technical setup)
"""

import os
import sys
import json
import time
import requests
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
import logging

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("MultiSourceFetcher")


@dataclass
class StockData:
    """Comprehensive stock data from multiple sources."""
    symbol: str
    timestamp: datetime = field(default_factory=datetime.now)

    # Price data
    price: float = 0.0
    open: float = 0.0
    high: float = 0.0
    low: float = 0.0
    close: float = 0.0
    volume: int = 0
    avg_volume: int = 0
    volume_ratio: float = 1.0

    # Pre/Post market
    premarket_price: float = 0.0
    premarket_change: float = 0.0
    premarket_volume: int = 0

    # Float & Shares
    shares_outstanding: int = 0
    float_shares: int = 0
    free_float: float = 0.0  # Percentage

    # Short data
    short_interest: float = 0.0  # As percentage of float
    short_ratio: float = 0.0  # Days to cover

    # Fundamentals
    market_cap: float = 0.0
    sector: str = ""
    industry: str = ""

    # News & Sentiment
    news: List[Dict] = field(default_factory=list)
    news_sentiment: float = 0.0  # -1 to 1
    catalyst_detected: bool = False
    catalyst_type: str = ""

    # Technical
    fifty_two_week_high: float = 0.0
    fifty_two_week_low: float = 0.0
    sma_20: float = 0.0
    sma_50: float = 0.0
    rsi: float = 50.0

    # Runner score components
    float_score: float = 0.0
    volume_score: float = 0.0
    momentum_score: float = 0.0
    catalyst_score: float = 0.0
    technical_score: float = 0.0
    total_runner_score: float = 0.0

    def to_dict(self) -> Dict:
        return {
            'symbol': self.symbol,
            'price': self.price,
            'volume': self.volume,
            'avg_volume': self.avg_volume,
            'volume_ratio': self.volume_ratio,
            'float_shares': self.float_shares,
            'short_interest': self.short_interest,
            'premarket_change': self.premarket_change,
            'news_count': len(self.news),
            'catalyst_detected': self.catalyst_detected,
            'runner_score': self.total_runner_score,
        }


class MultiSourceFetcher:
    """
    Fetches and aggregates data from multiple free APIs.

    Usage:
        fetcher = MultiSourceFetcher(
            tiingo_key="your_key",
            finnhub_key="your_key",  # Get free at finnhub.io
            fmp_key="your_key",       # Get free at financialmodelingprep.com
            alpha_key="your_key",     # Get free at alphavantage.co
        )

        data = fetcher.get_runner_data("GME")
    """

    def __init__(
        self,
        tiingo_key: str = None,
        finnhub_key: str = None,
        fmp_key: str = None,
        alpha_key: str = None,
    ):
        # API Keys (from params or environment)
        self.tiingo_key = tiingo_key or os.environ.get("TIINGO_API_KEY")
        self.finnhub_key = finnhub_key or os.environ.get("FINNHUB_API_KEY")
        self.fmp_key = fmp_key or os.environ.get("FMP_API_KEY")
        self.alpha_key = alpha_key or os.environ.get("ALPHA_VANTAGE_API_KEY")

        # Rate limiting
        self.last_request_time = {}
        self.request_counts = {
            'tiingo': 0,
            'finnhub': 0,
            'fmp': 0,
            'alpha': 0,
        }

        # Cache
        self.cache = {}
        self.cache_ttl = 300  # 5 minutes

        # Log available APIs
        self._log_api_status()

    def _log_api_status(self):
        """Log which APIs are available."""
        apis = {
            'Tiingo': self.tiingo_key is not None,
            'Finnhub': self.finnhub_key is not None,
            'FMP': self.fmp_key is not None,
            'Alpha Vantage': self.alpha_key is not None,
        }

        available = [k for k, v in apis.items() if v]
        missing = [k for k, v in apis.items() if not v]

        logger.info(f"Available APIs: {', '.join(available) if available else 'None'}")
        if missing:
            logger.warning(f"Missing API keys: {', '.join(missing)}")
            logger.info("Get free keys at:")
            if 'Finnhub' in missing:
                logger.info("  Finnhub: https://finnhub.io/register")
            if 'FMP' in missing:
                logger.info("  FMP: https://site.financialmodelingprep.com/register")
            if 'Alpha Vantage' in missing:
                logger.info("  Alpha Vantage: https://www.alphavantage.co/support/#api-key")

    def _rate_limit(self, source: str, min_interval: float = 1.0):
        """Enforce rate limiting."""
        now = time.time()
        last = self.last_request_time.get(source, 0)

        if now - last < min_interval:
            time.sleep(min_interval - (now - last))

        self.last_request_time[source] = time.time()
        self.request_counts[source] += 1

    def _get_cached(self, key: str) -> Optional[Any]:
        """Get cached data if still valid."""
        if key in self.cache:
            data, timestamp = self.cache[key]
            if time.time() - timestamp < self.cache_ttl:
                return data
        return None

    def _set_cache(self, key: str, data: Any):
        """Cache data with timestamp."""
        self.cache[key] = (data, time.time())

    # ========================================
    # TIINGO API
    # ========================================

    def _tiingo_eod(self, symbol: str) -> Optional[Dict]:
        """Get EOD data from Tiingo."""
        if not self.tiingo_key:
            return None

        cache_key = f"tiingo_eod_{symbol}"
        cached = self._get_cached(cache_key)
        if cached:
            return cached

        try:
            self._rate_limit('tiingo')

            end = datetime.now()
            start = end - timedelta(days=60)

            url = f"https://api.tiingo.com/tiingo/daily/{symbol}/prices"
            params = {
                'startDate': start.strftime('%Y-%m-%d'),
                'endDate': end.strftime('%Y-%m-%d'),
                'token': self.tiingo_key,
            }

            response = requests.get(url, params=params, timeout=10)

            if response.status_code == 200:
                data = response.json()
                self._set_cache(cache_key, data)
                return data
            else:
                logger.warning(f"Tiingo EOD error for {symbol}: {response.status_code}")

        except Exception as e:
            logger.error(f"Tiingo EOD error: {e}")

        return None

    def _tiingo_news(self, symbol: str) -> List[Dict]:
        """Get news from Tiingo."""
        if not self.tiingo_key:
            return []

        cache_key = f"tiingo_news_{symbol}"
        cached = self._get_cached(cache_key)
        if cached:
            return cached

        try:
            self._rate_limit('tiingo')

            url = "https://api.tiingo.com/tiingo/news"
            params = {
                'tickers': symbol,
                'limit': 10,
                'token': self.tiingo_key,
            }

            response = requests.get(url, params=params, timeout=10)

            if response.status_code == 200:
                data = response.json()
                self._set_cache(cache_key, data)
                return data

        except Exception as e:
            logger.error(f"Tiingo news error: {e}")

        return []

    # ========================================
    # FINNHUB API
    # ========================================

    def _finnhub_quote(self, symbol: str) -> Optional[Dict]:
        """Get real-time quote from Finnhub."""
        if not self.finnhub_key:
            return None

        cache_key = f"finnhub_quote_{symbol}"
        cached = self._get_cached(cache_key)
        if cached:
            return cached

        try:
            self._rate_limit('finnhub', 1.0)  # 60/min = 1/sec

            url = f"https://finnhub.io/api/v1/quote"
            params = {'symbol': symbol, 'token': self.finnhub_key}

            response = requests.get(url, params=params, timeout=10)

            if response.status_code == 200:
                data = response.json()
                self._set_cache(cache_key, data)
                return data

        except Exception as e:
            logger.error(f"Finnhub quote error: {e}")

        return None

    def _finnhub_profile(self, symbol: str) -> Optional[Dict]:
        """Get company profile from Finnhub (includes some float data)."""
        if not self.finnhub_key:
            return None

        cache_key = f"finnhub_profile_{symbol}"
        cached = self._get_cached(cache_key)
        if cached:
            return cached

        try:
            self._rate_limit('finnhub', 1.0)

            url = f"https://finnhub.io/api/v1/stock/profile2"
            params = {'symbol': symbol, 'token': self.finnhub_key}

            response = requests.get(url, params=params, timeout=10)

            if response.status_code == 200:
                data = response.json()
                self._set_cache(cache_key, data)
                return data

        except Exception as e:
            logger.error(f"Finnhub profile error: {e}")

        return None

    def _finnhub_news(self, symbol: str) -> List[Dict]:
        """Get company news from Finnhub."""
        if not self.finnhub_key:
            return []

        cache_key = f"finnhub_news_{symbol}"
        cached = self._get_cached(cache_key)
        if cached:
            return cached

        try:
            self._rate_limit('finnhub', 1.0)

            end = datetime.now()
            start = end - timedelta(days=7)

            url = f"https://finnhub.io/api/v1/company-news"
            params = {
                'symbol': symbol,
                'from': start.strftime('%Y-%m-%d'),
                'to': end.strftime('%Y-%m-%d'),
                'token': self.finnhub_key,
            }

            response = requests.get(url, params=params, timeout=10)

            if response.status_code == 200:
                data = response.json()
                self._set_cache(cache_key, data)
                return data if isinstance(data, list) else []

        except Exception as e:
            logger.error(f"Finnhub news error: {e}")

        return []

    def _finnhub_insider_sentiment(self, symbol: str) -> Optional[Dict]:
        """Get insider sentiment from Finnhub."""
        if not self.finnhub_key:
            return None

        try:
            self._rate_limit('finnhub', 1.0)

            url = f"https://finnhub.io/api/v1/stock/insider-sentiment"
            params = {
                'symbol': symbol,
                'from': (datetime.now() - timedelta(days=90)).strftime('%Y-%m-%d'),
                'to': datetime.now().strftime('%Y-%m-%d'),
                'token': self.finnhub_key,
            }

            response = requests.get(url, params=params, timeout=10)

            if response.status_code == 200:
                return response.json()

        except Exception as e:
            logger.error(f"Finnhub insider sentiment error: {e}")

        return None

    # ========================================
    # FMP API
    # ========================================

    def _fmp_float(self, symbol: str) -> Optional[Dict]:
        """Get float data from Financial Modeling Prep."""
        if not self.fmp_key:
            return None

        cache_key = f"fmp_float_{symbol}"
        cached = self._get_cached(cache_key)
        if cached:
            return cached

        try:
            self._rate_limit('fmp', 0.5)

            url = f"https://financialmodelingprep.com/api/v4/shares_float"
            params = {'symbol': symbol, 'apikey': self.fmp_key}

            response = requests.get(url, params=params, timeout=10)

            if response.status_code == 200:
                data = response.json()
                if data and len(data) > 0:
                    self._set_cache(cache_key, data[0])
                    return data[0]

        except Exception as e:
            logger.error(f"FMP float error: {e}")

        return None

    def _fmp_quote(self, symbol: str) -> Optional[Dict]:
        """Get quote from FMP (includes pre/post market)."""
        if not self.fmp_key:
            return None

        cache_key = f"fmp_quote_{symbol}"
        cached = self._get_cached(cache_key)
        if cached:
            return cached

        try:
            self._rate_limit('fmp', 0.5)

            url = f"https://financialmodelingprep.com/api/v3/quote/{symbol}"
            params = {'apikey': self.fmp_key}

            response = requests.get(url, params=params, timeout=10)

            if response.status_code == 200:
                data = response.json()
                if data and len(data) > 0:
                    self._set_cache(cache_key, data[0])
                    return data[0]

        except Exception as e:
            logger.error(f"FMP quote error: {e}")

        return None

    def _fmp_profile(self, symbol: str) -> Optional[Dict]:
        """Get company profile from FMP."""
        if not self.fmp_key:
            return None

        cache_key = f"fmp_profile_{symbol}"
        cached = self._get_cached(cache_key)
        if cached:
            return cached

        try:
            self._rate_limit('fmp', 0.5)

            url = f"https://financialmodelingprep.com/api/v3/profile/{symbol}"
            params = {'apikey': self.fmp_key}

            response = requests.get(url, params=params, timeout=10)

            if response.status_code == 200:
                data = response.json()
                if data and len(data) > 0:
                    self._set_cache(cache_key, data[0])
                    return data[0]

        except Exception as e:
            logger.error(f"FMP profile error: {e}")

        return None

    # ========================================
    # ALPHA VANTAGE API
    # ========================================

    def _alpha_news_sentiment(self, symbol: str) -> Optional[Dict]:
        """Get news with sentiment from Alpha Vantage."""
        if not self.alpha_key:
            return None

        cache_key = f"alpha_news_{symbol}"
        cached = self._get_cached(cache_key)
        if cached:
            return cached

        try:
            self._rate_limit('alpha', 3.0)  # 25/day = slow

            url = "https://www.alphavantage.co/query"
            params = {
                'function': 'NEWS_SENTIMENT',
                'tickers': symbol,
                'apikey': self.alpha_key,
            }

            response = requests.get(url, params=params, timeout=15)

            if response.status_code == 200:
                data = response.json()
                self._set_cache(cache_key, data)
                return data

        except Exception as e:
            logger.error(f"Alpha Vantage news error: {e}")

        return None

    def _alpha_overview(self, symbol: str) -> Optional[Dict]:
        """Get company overview from Alpha Vantage."""
        if not self.alpha_key:
            return None

        cache_key = f"alpha_overview_{symbol}"
        cached = self._get_cached(cache_key)
        if cached:
            return cached

        try:
            self._rate_limit('alpha', 3.0)

            url = "https://www.alphavantage.co/query"
            params = {
                'function': 'OVERVIEW',
                'symbol': symbol,
                'apikey': self.alpha_key,
            }

            response = requests.get(url, params=params, timeout=15)

            if response.status_code == 200:
                data = response.json()
                if 'Symbol' in data:  # Valid response
                    self._set_cache(cache_key, data)
                    return data

        except Exception as e:
            logger.error(f"Alpha Vantage overview error: {e}")

        return None

    # ========================================
    # AGGREGATION
    # ========================================

    def get_stock_data(self, symbol: str) -> StockData:
        """
        Get comprehensive stock data from all available sources.

        Aggregates:
        - Price/volume from Tiingo or Finnhub
        - Float data from FMP
        - News from multiple sources
        - Sentiment from Alpha Vantage
        """
        data = StockData(symbol=symbol)

        logger.info(f"Fetching data for {symbol}...")

        # 1. Get price data (Tiingo primary, Finnhub backup)
        eod = self._tiingo_eod(symbol)
        if eod and len(eod) > 0:
            latest = eod[-1]
            data.open = latest.get('adjOpen', latest.get('open', 0))
            data.high = latest.get('adjHigh', latest.get('high', 0))
            data.low = latest.get('adjLow', latest.get('low', 0))
            data.close = latest.get('adjClose', latest.get('close', 0))
            data.price = data.close
            data.volume = latest.get('adjVolume', latest.get('volume', 0))

            # Calculate average volume (20 day)
            if len(eod) >= 20:
                volumes = [d.get('adjVolume', d.get('volume', 0)) for d in eod[-20:]]
                data.avg_volume = int(sum(volumes) / len(volumes))
                if data.avg_volume > 0:
                    data.volume_ratio = data.volume / data.avg_volume

            # 52-week high/low
            if len(eod) >= 252:
                highs = [d.get('adjHigh', d.get('high', 0)) for d in eod[-252:]]
                lows = [d.get('adjLow', d.get('low', 0)) for d in eod[-252:]]
                data.fifty_two_week_high = max(highs)
                data.fifty_two_week_low = min(lows)

            # Calculate SMAs
            if len(eod) >= 50:
                closes = [d.get('adjClose', d.get('close', 0)) for d in eod]
                data.sma_20 = sum(closes[-20:]) / 20
                data.sma_50 = sum(closes[-50:]) / 50

        # 2. Get real-time quote (Finnhub)
        fh_quote = self._finnhub_quote(symbol)
        if fh_quote:
            if fh_quote.get('c', 0) > 0:
                data.price = fh_quote['c']
            data.open = fh_quote.get('o', data.open)
            data.high = fh_quote.get('h', data.high)
            data.low = fh_quote.get('l', data.low)

            # Pre-market from previous close
            pc = fh_quote.get('pc', 0)
            if pc > 0 and data.price > 0:
                data.premarket_change = (data.price - pc) / pc

        # 3. Get FMP quote (includes pre/post market)
        fmp_quote = self._fmp_quote(symbol)
        if fmp_quote:
            data.market_cap = fmp_quote.get('marketCap', 0)
            data.avg_volume = fmp_quote.get('avgVolume', data.avg_volume)
            data.fifty_two_week_high = fmp_quote.get('yearHigh', data.fifty_two_week_high)
            data.fifty_two_week_low = fmp_quote.get('yearLow', data.fifty_two_week_low)

            # Volume ratio
            if data.avg_volume > 0 and data.volume > 0:
                data.volume_ratio = data.volume / data.avg_volume

        # 4. Get float data (FMP)
        fmp_float = self._fmp_float(symbol)
        if fmp_float:
            data.float_shares = fmp_float.get('floatShares', 0)
            data.shares_outstanding = fmp_float.get('outstandingShares', 0)
            if data.shares_outstanding > 0:
                data.free_float = (data.float_shares / data.shares_outstanding) * 100

        # 5. Get company profile (Finnhub or FMP)
        fh_profile = self._finnhub_profile(symbol)
        if fh_profile:
            data.shares_outstanding = fh_profile.get('shareOutstanding', data.shares_outstanding) * 1_000_000
            data.market_cap = fh_profile.get('marketCapitalization', data.market_cap) * 1_000_000
            data.sector = fh_profile.get('finnhubIndustry', '')

        fmp_profile = self._fmp_profile(symbol)
        if fmp_profile:
            data.sector = fmp_profile.get('sector', data.sector)
            data.industry = fmp_profile.get('industry', '')
            if not data.shares_outstanding:
                data.shares_outstanding = fmp_profile.get('mktCap', 0) / data.price if data.price > 0 else 0

        # 6. Get news from multiple sources
        all_news = []

        tiingo_news = self._tiingo_news(symbol)
        for item in tiingo_news[:5]:
            all_news.append({
                'headline': item.get('title', ''),
                'source': item.get('source', 'Tiingo'),
                'url': item.get('url', ''),
                'published': item.get('publishedDate', ''),
            })

        finnhub_news = self._finnhub_news(symbol)
        for item in finnhub_news[:5]:
            all_news.append({
                'headline': item.get('headline', ''),
                'source': item.get('source', 'Finnhub'),
                'url': item.get('url', ''),
                'published': datetime.fromtimestamp(item.get('datetime', 0)).isoformat() if item.get('datetime') else '',
            })

        data.news = all_news

        # 7. Get sentiment (Alpha Vantage)
        alpha_news = self._alpha_news_sentiment(symbol)
        if alpha_news and 'feed' in alpha_news:
            sentiments = []
            for item in alpha_news['feed'][:10]:
                for ticker in item.get('ticker_sentiment', []):
                    if ticker.get('ticker') == symbol:
                        score = float(ticker.get('ticker_sentiment_score', 0))
                        sentiments.append(score)

            if sentiments:
                data.news_sentiment = sum(sentiments) / len(sentiments)

        # 8. Detect catalysts
        data.catalyst_detected, data.catalyst_type = self._detect_catalyst(data.news)

        # 9. Calculate runner scores
        self._calculate_runner_scores(data)

        logger.info(f"{symbol}: Price=${data.price:.2f}, Float={data.float_shares:,}, "
                   f"Vol Ratio={data.volume_ratio:.1f}x, Runner Score={data.total_runner_score:.0f}")

        return data

    def _detect_catalyst(self, news: List[Dict]) -> tuple:
        """Detect if there's a catalyst in the news."""
        strong_catalysts = [
            ('fda', 'FDA'),
            ('approval', 'Regulatory'),
            ('patent', 'Patent'),
            ('contract', 'Contract'),
            ('acquisition', 'M&A'),
            ('merger', 'M&A'),
            ('buyout', 'M&A'),
            ('earnings beat', 'Earnings'),
            ('guidance raise', 'Guidance'),
            ('partnership', 'Partnership'),
            ('breakthrough', 'Breakthrough'),
            ('short squeeze', 'Short Squeeze'),
            ('gamma squeeze', 'Gamma Squeeze'),
        ]

        medium_catalysts = [
            ('upgrade', 'Analyst'),
            ('buy rating', 'Analyst'),
            ('price target', 'Analyst'),
            ('revenue', 'Financials'),
            ('growth', 'Growth'),
            ('expansion', 'Expansion'),
            ('launch', 'Product'),
            ('sec filing', 'Filing'),
        ]

        for item in news[:10]:
            headline = item.get('headline', '').lower()

            for keyword, cat_type in strong_catalysts:
                if keyword in headline:
                    return True, cat_type

            for keyword, cat_type in medium_catalysts:
                if keyword in headline:
                    return True, cat_type

        return False, ""

    def _calculate_runner_scores(self, data: StockData):
        """Calculate runner potential scores."""
        # Float score (0-25)
        # Low float = high squeeze potential
        if data.float_shares > 0:
            if data.float_shares < 5_000_000:
                data.float_score = 25
            elif data.float_shares < 10_000_000:
                data.float_score = 20
            elif data.float_shares < 20_000_000:
                data.float_score = 15
            elif data.float_shares < 50_000_000:
                data.float_score = 10
            else:
                data.float_score = 5

        # Volume score (0-25)
        if data.volume_ratio >= 10:
            data.volume_score = 25
        elif data.volume_ratio >= 5:
            data.volume_score = 20
        elif data.volume_ratio >= 3:
            data.volume_score = 15
        elif data.volume_ratio >= 2:
            data.volume_score = 10
        elif data.volume_ratio >= 1.5:
            data.volume_score = 5

        # Momentum score (0-20)
        if data.premarket_change >= 0.20:
            data.momentum_score = 20
        elif data.premarket_change >= 0.10:
            data.momentum_score = 15
        elif data.premarket_change >= 0.05:
            data.momentum_score = 10
        elif data.premarket_change >= 0.02:
            data.momentum_score = 5

        # Catalyst score (0-15)
        if data.catalyst_detected:
            if data.catalyst_type in ['FDA', 'M&A', 'Short Squeeze', 'Gamma Squeeze']:
                data.catalyst_score = 15
            else:
                data.catalyst_score = 10

        # Technical score (0-15)
        if data.price > 0 and data.fifty_two_week_high > 0:
            pct_from_high = (data.fifty_two_week_high - data.price) / data.fifty_two_week_high
            if pct_from_high <= 0.05:  # Within 5% of 52-week high
                data.technical_score = 15
            elif pct_from_high <= 0.10:
                data.technical_score = 10
            elif pct_from_high <= 0.20:
                data.technical_score = 5

        # Total score
        data.total_runner_score = (
            data.float_score +
            data.volume_score +
            data.momentum_score +
            data.catalyst_score +
            data.technical_score
        )

    def scan_for_runners(self, symbols: List[str], min_score: float = 40) -> List[StockData]:
        """
        Scan multiple symbols for runner potential.

        Returns list sorted by runner score.
        """
        results = []

        logger.info(f"Scanning {len(symbols)} symbols for runners...")

        for symbol in symbols:
            try:
                data = self.get_stock_data(symbol)
                if data.total_runner_score >= min_score:
                    results.append(data)
            except Exception as e:
                logger.error(f"Error scanning {symbol}: {e}")

        # Sort by score descending
        results.sort(key=lambda x: x.total_runner_score, reverse=True)

        return results

    def get_api_usage(self) -> Dict:
        """Get API usage stats."""
        return {
            'tiingo_requests': self.request_counts['tiingo'],
            'finnhub_requests': self.request_counts['finnhub'],
            'fmp_requests': self.request_counts['fmp'],
            'alpha_requests': self.request_counts['alpha'],
            'cache_size': len(self.cache),
        }


# ============================================================
# Test
# ============================================================

if __name__ == "__main__":
    print("""
╔══════════════════════════════════════════════════════════════╗
║              MULTI-SOURCE DATA FETCHER TEST                   ║
╚══════════════════════════════════════════════════════════════╝
""")

    fetcher = MultiSourceFetcher()

    # Test with a few symbols
    symbols = ['GME', 'AMC', 'AAPL']

    print("\nFetching data for test symbols...")
    print("-" * 60)

    for symbol in symbols:
        data = fetcher.get_stock_data(symbol)

        print(f"""
{symbol}:
  Price: ${data.price:.2f}
  Volume: {data.volume:,} ({data.volume_ratio:.1f}x avg)
  Float: {data.float_shares:,} shares
  Market Cap: ${data.market_cap/1e9:.2f}B
  Pre-market: {data.premarket_change:+.1%}
  Catalyst: {data.catalyst_type if data.catalyst_detected else 'None'}
  News: {len(data.news)} articles
  Sentiment: {data.news_sentiment:+.2f}

  Runner Scores:
    Float:     {data.float_score}/25
    Volume:    {data.volume_score}/25
    Momentum:  {data.momentum_score}/20
    Catalyst:  {data.catalyst_score}/15
    Technical: {data.technical_score}/15
    TOTAL:     {data.total_runner_score}/100
""")

    print("-" * 60)
    print(f"API Usage: {fetcher.get_api_usage()}")

    print("""
To enable all data sources, set environment variables:
  export TIINGO_API_KEY=your_key
  export FINNHUB_API_KEY=your_key
  export FMP_API_KEY=your_key
  export ALPHA_VANTAGE_API_KEY=your_key

Get free API keys:
  Finnhub: https://finnhub.io/register
  FMP: https://site.financialmodelingprep.com/register
  Alpha Vantage: https://www.alphavantage.co/support/#api-key
""")
