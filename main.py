"""BTC race bot: sharp-drop bounce catcher, long only, all-in.

Strategy (validated on this race's dev window, wire protocol, 2 runs
byte-identical: net PnL +$2.98, max drawdown 0.26%, 1 round trip
buy bar 431 -> sell bar 468; the plain SMA dip-buy that won the
previous race loses on this window, a steady -4.9% bleed, so this bot
waits for a confirmed bounce instead of buying every dip):
- Track the 1-minute closes of CBBTC.
- Buy all-in only when the 30-bar range has dropped at least 1.2%
  (a real sharp drop, not a slow bleed) AND the latest close has
  bounced at least 0.5% off the 30-bar low (the reversal is confirmed).
- Sell the whole position when the close reaches +0.6% above entry
  (take profit), or falls 0.3% below the highest close since entry
  (trailing stop), or falls 0.5% below entry (stop-loss), or 90 bars
  (1.5 hours) have passed since entry without an exit (max hold).
- One position at a time, no leverage, no shorts.

Deterministic: pure float arithmetic on the closes, no clock, no random,
no environment reads, so two runs produce byte-identical order logs.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "vendor"))
import makefun_bars

SYMBOL = "CBBTC"
WIN = 30
DROP = 0.012
BOUNCE = 0.005
TP = 0.006
TRAIL = 0.003
SL = 0.005
MAX_HOLD = 90
MAX_SLIP = 100

closes = []
entry_idx = -1
entry_close = 0.0
peak_close = 0.0


def on_batch(state, batch):
    global entry_idx, entry_close, peak_close
    if state.warming_up:
        return None
    for bar in batch.get("bars", []):
        if bar.get("symbol") == SYMBOL:
            closes.append(int(bar["c"]) / 1e5)
    if len(closes) < WIN:
        return None
    close = closes[-1]
    holding = state.positions.get(SYMBOL)
    if holding is None:
        window = closes[-WIN:]
        hi = max(window)
        lo = min(window)
        if (hi - lo) / hi >= DROP and close >= lo * (1 + BOUNCE):
            notional = min(state.cash, state.weight_room(SYMBOL))
            if notional >= int(state.hello["fees"]["min_notional_quote_units"]):
                entry_idx = len(closes) - 1
                entry_close = close
                peak_close = close
                return [{"side": "buy", "symbol": SYMBOL,
                         "notional_quote_units": notional,
                         "max_slippage_bps": MAX_SLIP}]
        return None
    peak_close = max(peak_close, close)
    if close >= entry_close * (1 + TP):
        return [{"side": "sell", "symbol": SYMBOL, "qty": holding.qty,
                 "max_slippage_bps": MAX_SLIP}]
    if close <= peak_close * (1 - TRAIL):
        return [{"side": "sell", "symbol": SYMBOL, "qty": holding.qty,
                 "max_slippage_bps": MAX_SLIP}]
    if close <= entry_close * (1 - SL):
        return [{"side": "sell", "symbol": SYMBOL, "qty": holding.qty,
                 "max_slippage_bps": MAX_SLIP}]
    if len(closes) - 1 - entry_idx >= MAX_HOLD:
        return [{"side": "sell", "symbol": SYMBOL, "qty": holding.qty,
                 "max_slippage_bps": MAX_SLIP}]
    return None


makefun_bars.run(on_batch)
