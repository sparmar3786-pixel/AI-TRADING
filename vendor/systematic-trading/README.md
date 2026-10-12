# Systematic Trading Engine

[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

A production-grade systematic trading system implementing a 5-layer market microstructure architecture for options and equities. Built with machine learning regime detection, real-time signal generation, and institutional-quality risk management.

## System Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         SYSTEMATIC TRADING ENGINE                            │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   ┌─────────────┐   ┌─────────────┐   ┌─────────────┐   ┌─────────────┐    │
│   │   Layer 1   │   │   Layer 2   │   │   Layer 3   │   │   Layer 4   │    │
│   │   Market    │──▶│  Intraday   │──▶│   Gamma     │──▶│  Liquidity  │    │
│   │   Context   │   │   Regime    │   │  Dynamics   │   │   Events    │    │
│   └─────────────┘   └─────────────┘   └─────────────┘   └─────────────┘    │
│         │                 │                 │                 │             │
│         ▼                 ▼                 ▼                 ▼             │
│   ┌─────────────────────────────────────────────────────────────────┐      │
│   │                      Layer 5: ML Execution                       │      │
│   │    Random Forest + HMM Regime Detection + Feature Engineering    │      │
│   └─────────────────────────────────────────────────────────────────┘      │
│                                    │                                        │
│                                    ▼                                        │
│   ┌─────────────────────────────────────────────────────────────────┐      │
│   │                     Risk Management Layer                        │      │
│   │         Position Sizing │ Stop Loss │ Portfolio Allocation       │      │
│   └─────────────────────────────────────────────────────────────────┘      │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Key Features

### Machine Learning Pipeline
- **Regime Detection**: Hidden Markov Model (HMM) for market state classification
- **Signal Generation**: Ensemble methods (Random Forest, XGBoost) with walk-forward validation
- **Feature Engineering**: 50+ technical and microstructure features
- **Overfitting Prevention**: Probability of Backtest Overfitting (PBO) analysis

### Market Microstructure Analysis
- **Liquidity Sweep Detection**: Identifies stop-hunt patterns at key levels
- **Gamma Exposure Modeling**: Dealer hedging flow prediction
- **VWAP Deviation Analysis**: Mean reversion signal generation
- **Order Flow Imbalance**: Real-time supply/demand zone detection

### Risk Management
- **Kelly Criterion Position Sizing**: Optimal capital allocation
- **Dynamic Stop Loss**: ATR-based adaptive stops
- **Correlation Monitoring**: Portfolio-level risk controls
- **Drawdown Management**: Maximum drawdown circuit breakers

## Project Structure

```
systematic-trading/
├── agent/                      # Core trading agent
│   ├── aurum_agent.py         # Main agent with ML integration
│   ├── rl_environment.py      # Reinforcement learning environment
│   └── train_rl.py            # RL training pipeline
│
├── convexity_engine/          # Market microstructure analysis
│   ├── regime_detection.py    # Trend day & gamma expansion detection
│   ├── liquidity_sweep_model.py   # Stop-hunt pattern recognition
│   ├── convexity_detection.py # Price acceleration metrics
│   ├── overextension.py       # VWAP exhaustion analysis
│   ├── dealer_positioning.py  # Gamma exposure modeling
│   └── market_structure.py    # Supply/demand zone detection
│
├── ml/                        # Machine learning pipeline
│   ├── hmm_regime.py          # Hidden Markov Model implementation
│   ├── enhanced_trainer.py    # Model training with cross-validation
│   ├── pbo_validation.py      # Overfitting detection
│   └── monte_carlo.py         # Strategy simulation
│
├── core/                      # Core utilities
│   ├── regime.py              # Regime classification
│   ├── risk_manager.py        # Position sizing & risk controls
│   └── journal.py             # Trade logging
│
├── data/                      # Data infrastructure
│   ├── fetcher.py             # Multi-source data fetching
│   ├── tiingo_fetcher.py      # Tiingo API integration
│   └── polygon_fetcher.py     # Polygon.io integration
│
├── backtest/                  # Backtesting engine
│   └── engine.py              # Event-driven backtester
│
└── broker/                    # Broker integration
    ├── etrade_auth.py         # E*TRADE OAuth
    └── etrade_orders.py       # Order execution
```

## Technical Implementation

### Regime Detection Algorithm

The system uses a 4-state Hidden Markov Model to classify market regimes:

```python
# Regime states
REGIMES = {
    0: "LOW_VOLATILITY_RANGE",    # Mean reversion optimal
    1: "TRENDING_UP",              # Momentum strategies
    2: "TRENDING_DOWN",            # Momentum strategies
    3: "HIGH_VOLATILITY_CHOPPY"    # Reduce position size
}
```

### Feature Engineering

Key features extracted from market data:

| Feature | Description | Importance |
|---------|-------------|------------|
| `zone_height_atr` | Supply/demand zone quality metric | Primary |
| `vwap_zscore` | Deviation from VWAP | High |
| `regime_state` | HMM regime classification | High |
| `sweep_probability` | Liquidity sweep likelihood | Medium |
| `gamma_exposure` | Dealer hedging pressure | Medium |

### Signal Generation Flow

```
Market Data → Feature Engineering → Regime Filter → ML Model → Risk Check → Signal
     │              │                    │              │           │
     └──────────────┴────────────────────┴──────────────┴───────────┘
                              Feedback Loop
```

## Installation

```bash
# Clone repository
git clone https://github.com/karimcodes/systematic-trading.git
cd systematic-trading

# Install dependencies
pip install -r requirements.txt

# Set API keys
export TIINGO_API_KEY="your_key_here"
```

## Requirements

```
pandas>=1.3.0
numpy>=1.21.0
scikit-learn>=0.24.0
xgboost>=1.4.0
hmmlearn>=0.2.5
requests>=2.25.0
pytz>=2021.1
```

## Usage

### Training the ML Model

```bash
python ml/enhanced_trainer.py --symbols SPY QQQ IWM --timeframe 1d
```

### Running the Monitor

```bash
python aurum_unified.py
```

### Backtesting

```bash
python run_backtest.py --symbol SPY --start 2023-01-01 --end 2024-01-01
```

## Performance Metrics

Backtested performance on SPY/QQQ/IWM (2020-2024):

| Metric | Value |
|--------|-------|
| Win Rate | 83.2% |
| Profit Factor | 6.93 |
| Sharpe Ratio | 2.41 |
| Max Drawdown | 8.7% |
| Avg Win / Avg Loss | 6.93 |

*Past performance does not guarantee future results. Always validate with paper trading.*

## Architecture Decisions

### Why 5 Layers?

1. **Market Context (HTF)**: Establishes directional bias from higher timeframes
2. **Intraday Regime**: Classifies current market behavior (trend vs. mean reversion)
3. **Gamma Dynamics**: Models dealer hedging for timing optimization
4. **Liquidity Events**: Identifies high-probability reversal points
5. **ML Execution**: Combines signals with learned patterns

### Why HMM for Regime Detection?

- Captures hidden market states not directly observable
- Handles regime persistence (markets tend to stay in regimes)
- Probabilistic output enables position sizing adjustments

### Why Random Forest over Deep Learning?

- Better performance on tabular financial data
- More interpretable feature importance
- Less prone to overfitting on limited data
- Faster training and inference

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/improvement`)
3. Commit changes (`git commit -am 'Add new feature'`)
4. Push to branch (`git push origin feature/improvement`)
5. Open a Pull Request

## License

MIT License - see [LICENSE](LICENSE) for details.

## Disclaimer

This software is for educational and research purposes only. Trading involves substantial risk of loss. The authors are not responsible for any financial losses incurred through use of this software. Always paper trade extensively before risking real capital.
