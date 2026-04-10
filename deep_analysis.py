"""
Deep technical analysis module — computes 17 techniques + confluence score.

Every public compute_* function returns a standardised log dict:
    {"name": str, "values": dict, "signal": "BULLISH"|"BEARISH"|"NEUTRAL", "reason": str}

All computation is pure Python/pandas/numpy — no AI involved.
"""

import pandas as pd
import pandas_ta as ta
import numpy as np
from typing import Literal

Signal = Literal["BULLISH", "BEARISH", "NEUTRAL"]


def _log(name: str, values: dict, signal: Signal, reason: str) -> dict:
    return {"name": name, "values": values, "signal": signal, "reason": reason}


# ---------------------------------------------------------------------------
# 1. CORE TREND
# ---------------------------------------------------------------------------

def compute_renko(df: pd.DataFrame, atr_length: int = 14) -> dict:
    """Renko bricks using ATR-based brick size."""
    try:
        close = df["Close"]
        high, low = df["High"], df["Low"]

        atr_series = ta.atr(high, low, close, length=atr_length)
        brick_size = round(float(atr_series.iloc[-1]), 2) if atr_series is not None and not np.isnan(atr_series.iloc[-1]) else round(float(close.iloc[-1]) * 0.01, 2)
        brick_size = max(brick_size, 0.01)

        bricks = []  # list of "UP" / "DOWN"
        base_price = float(close.iloc[0])
        direction = None

        for price in close.iloc[1:].values:
            price = float(price)
            if direction is None:
                if price - base_price >= brick_size:
                    while price - base_price >= brick_size:
                        bricks.append("UP")
                        base_price += brick_size
                    direction = "UP"
                elif base_price - price >= brick_size:
                    while base_price - price >= brick_size:
                        bricks.append("DOWN")
                        base_price -= brick_size
                    direction = "DOWN"
            elif direction == "UP":
                while price - base_price >= brick_size:
                    bricks.append("UP")
                    base_price += brick_size
                if base_price - price >= 2 * brick_size:
                    base_price -= brick_size
                    direction = "DOWN"
                    while base_price - price >= brick_size:
                        bricks.append("DOWN")
                        base_price -= brick_size
            elif direction == "DOWN":
                while base_price - price >= brick_size:
                    bricks.append("DOWN")
                    base_price -= brick_size
                if price - base_price >= 2 * brick_size:
                    base_price += brick_size
                    direction = "UP"
                    while price - base_price >= brick_size:
                        bricks.append("UP")
                        base_price += brick_size

        if not bricks:
            return _log("Renko", {"brick_size": brick_size}, "NEUTRAL", "No bricks formed — price range too narrow")

        # Count consecutive same-direction bricks at tail
        consecutive = 1
        for i in range(len(bricks) - 2, -1, -1):
            if bricks[i] == bricks[-1]:
                consecutive += 1
            else:
                break

        current_trend = bricks[-1]
        last_reversal_price = round(base_price, 2)

        vals = {
            "brick_size": brick_size,
            "total_bricks": len(bricks),
            "current_trend": current_trend,
            "consecutive_bricks": consecutive,
            "last_reversal_price": last_reversal_price,
        }

        if current_trend == "UP" and consecutive >= 3:
            return _log("Renko", vals, "BULLISH", f"Uptrend with {consecutive} consecutive UP bricks")
        elif current_trend == "DOWN" and consecutive >= 3:
            return _log("Renko", vals, "BEARISH", f"Downtrend with {consecutive} consecutive DOWN bricks")
        else:
            return _log("Renko", vals, "NEUTRAL", f"Trend {current_trend} but only {consecutive} consecutive bricks — not strong enough")

    except Exception as e:
        return _log("Renko", {}, "NEUTRAL", f"Error: {e}")


def compute_point_and_figure(df: pd.DataFrame, box_size: float | None = None, reversal: int = 3) -> dict:
    """Point & Figure chart with breakout detection."""
    try:
        close = df["Close"]
        high, low = df["High"], df["Low"]

        if box_size is None:
            atr_series = ta.atr(high, low, close, length=14)
            atr_val = float(atr_series.iloc[-1]) if atr_series is not None and not np.isnan(atr_series.iloc[-1]) else float(close.iloc[-1]) * 0.01
            box_size = round(atr_val / 2, 2)
        box_size = max(box_size, 0.01)

        # columns: list of dicts {direction, high, low, boxes}
        columns = []
        col = {"direction": "X", "high": float(close.iloc[0]), "low": float(close.iloc[0]), "boxes": 0}

        for price in close.iloc[1:].values:
            price = float(price)
            if col["direction"] == "X":
                # Extend up
                while price >= col["high"] + box_size:
                    col["high"] += box_size
                    col["boxes"] += 1
                # Check reversal
                if col["high"] - price >= reversal * box_size:
                    columns.append(col.copy())
                    col = {"direction": "O", "high": col["high"] - box_size, "low": col["high"] - box_size, "boxes": 0}
                    while col["low"] - price >= box_size:
                        col["low"] -= box_size
                        col["boxes"] += 1
            else:  # O column
                while price <= col["low"] - box_size:
                    col["low"] -= box_size
                    col["boxes"] += 1
                if price - col["low"] >= reversal * box_size:
                    columns.append(col.copy())
                    col = {"direction": "X", "low": col["low"] + box_size, "high": col["low"] + box_size, "boxes": 0}
                    while price >= col["high"] + box_size:
                        col["high"] += box_size
                        col["boxes"] += 1

        columns.append(col)  # append the current active column

        # Breakout detection
        breakout = "NONE"
        price_target = None
        x_columns = [c for c in columns if c["direction"] == "X"]
        o_columns = [c for c in columns if c["direction"] == "O"]

        if len(x_columns) >= 2 and col["direction"] == "X":
            if col["high"] > x_columns[-2]["high"]:
                breakout = "DOUBLE_TOP_BREAKOUT"
                price_target = round(col["high"] + col["boxes"] * box_size, 2)
        elif len(o_columns) >= 2 and col["direction"] == "O":
            if col["low"] < o_columns[-2]["low"]:
                breakout = "DOUBLE_BOTTOM_BREAKDOWN"
                price_target = round(col["low"] - col["boxes"] * box_size, 2)

        vals = {
            "box_size": box_size,
            "reversal": reversal,
            "total_columns": len(columns),
            "current_direction": col["direction"],
            "current_column_boxes": col["boxes"],
            "breakout_signal": breakout,
            "price_target": price_target,
        }

        if breakout == "DOUBLE_TOP_BREAKOUT":
            return _log("Point & Figure", vals, "BULLISH", f"Double-top breakout — price target {price_target}")
        elif breakout == "DOUBLE_BOTTOM_BREAKDOWN":
            return _log("Point & Figure", vals, "BEARISH", f"Double-bottom breakdown — price target {price_target}")
        elif col["direction"] == "X":
            return _log("Point & Figure", vals, "NEUTRAL", f"In X (up) column with {col['boxes']} boxes — no breakout yet")
        else:
            return _log("Point & Figure", vals, "NEUTRAL", f"In O (down) column with {col['boxes']} boxes — no breakdown yet")

    except Exception as e:
        return _log("Point & Figure", {}, "NEUTRAL", f"Error: {e}")


def compute_ema_trend(df: pd.DataFrame) -> dict:
    """EMA(20) and EMA(50) trend analysis."""
    try:
        close = df["Close"]
        ema20 = ta.ema(close, length=20)
        ema50 = ta.ema(close, length=50)

        if ema20 is None or ema50 is None:
            return _log("EMA Trend", {}, "NEUTRAL", "Insufficient data for EMA calculation")

        price = round(float(close.iloc[-1]), 2)
        e20 = round(float(ema20.iloc[-1]), 2)
        e50 = round(float(ema50.iloc[-1]), 2)
        pct_vs_20 = round((price - e20) / e20 * 100, 2)
        pct_vs_50 = round((price - e50) / e50 * 100, 2)

        vals = {
            "price": price,
            "ema20": e20,
            "ema50": e50,
            "price_vs_ema20_pct": pct_vs_20,
            "price_vs_ema50_pct": pct_vs_50,
            "ema20_above_ema50": e20 > e50,
        }

        if price > e20 > e50:
            return _log("EMA Trend", vals, "BULLISH", f"Price ({price}) > EMA20 ({e20}) > EMA50 ({e50}) — strong uptrend")
        elif price < e20 < e50:
            return _log("EMA Trend", vals, "BEARISH", f"Price ({price}) < EMA20 ({e20}) < EMA50 ({e50}) — strong downtrend")
        else:
            return _log("EMA Trend", vals, "NEUTRAL", f"Mixed — price={price}, EMA20={e20}, EMA50={e50}")

    except Exception as e:
        return _log("EMA Trend", {}, "NEUTRAL", f"Error: {e}")


def compute_adx(df: pd.DataFrame, length: int = 14) -> dict:
    """ADX trend strength indicator."""
    try:
        adx_df = ta.adx(df["High"], df["Low"], df["Close"], length=length)
        if adx_df is None:
            return _log("ADX", {}, "NEUTRAL", "Insufficient data for ADX")

        adx_val = round(float(adx_df[f"ADX_{length}"].iloc[-1]), 2)
        di_plus = round(float(adx_df[f"DMP_{length}"].iloc[-1]), 2)
        di_minus = round(float(adx_df[f"DMN_{length}"].iloc[-1]), 2)

        vals = {"adx": adx_val, "di_plus": di_plus, "di_minus": di_minus}

        if adx_val > 25 and di_plus > di_minus:
            return _log("ADX", vals, "BULLISH", f"Strong uptrend (ADX={adx_val}, DI+={di_plus} > DI-={di_minus})")
        elif adx_val > 25 and di_minus > di_plus:
            return _log("ADX", vals, "BEARISH", f"Strong downtrend (ADX={adx_val}, DI-={di_minus} > DI+={di_plus})")
        else:
            return _log("ADX", vals, "NEUTRAL", f"Weak/no trend (ADX={adx_val}) — ranging market")

    except Exception as e:
        return _log("ADX", {}, "NEUTRAL", f"Error: {e}")


# ---------------------------------------------------------------------------
# 2. MOMENTUM
# ---------------------------------------------------------------------------

def compute_rsi(df: pd.DataFrame, length: int = 14) -> dict:
    """RSI momentum indicator."""
    try:
        rsi = ta.rsi(df["Close"], length=length)
        if rsi is None:
            return _log("RSI", {}, "NEUTRAL", "Insufficient data")

        val = round(float(rsi.iloc[-1]), 2)
        vals = {"rsi": val}

        if val < 30:
            return _log("RSI", vals, "BULLISH", f"Oversold at {val} — bounce potential")
        elif val > 70:
            return _log("RSI", vals, "BEARISH", f"Overbought at {val} — pullback risk")
        elif val < 45:
            return _log("RSI", vals, "NEUTRAL", f"RSI at {val} — leaning weak but not oversold")
        elif val > 55:
            return _log("RSI", vals, "NEUTRAL", f"RSI at {val} — leaning strong but not overbought")
        else:
            return _log("RSI", vals, "NEUTRAL", f"RSI at {val} — neutral zone")

    except Exception as e:
        return _log("RSI", {}, "NEUTRAL", f"Error: {e}")


def compute_macd(df: pd.DataFrame) -> dict:
    """MACD momentum with histogram trend."""
    try:
        macd_df = ta.macd(df["Close"], fast=12, slow=26, signal=9)
        if macd_df is None:
            return _log("MACD", {}, "NEUTRAL", "Insufficient data")

        macd_val = round(float(macd_df["MACD_12_26_9"].iloc[-1]), 4)
        signal_val = round(float(macd_df["MACDs_12_26_9"].iloc[-1]), 4)
        hist = round(float(macd_df["MACDh_12_26_9"].iloc[-1]), 4)
        hist_prev = round(float(macd_df["MACDh_12_26_9"].iloc[-2]), 4)
        hist_increasing = hist > hist_prev

        # Check for crossover in last 3 bars
        crossover = "none"
        hist_series = macd_df["MACDh_12_26_9"].iloc[-3:]
        if len(hist_series) >= 2:
            for i in range(1, len(hist_series)):
                if hist_series.iloc[i] > 0 and hist_series.iloc[i - 1] <= 0:
                    crossover = "bullish_crossover"
                elif hist_series.iloc[i] < 0 and hist_series.iloc[i - 1] >= 0:
                    crossover = "bearish_crossover"

        vals = {
            "macd": macd_val,
            "signal_line": signal_val,
            "histogram": hist,
            "hist_increasing": hist_increasing,
            "crossover": crossover,
        }

        if hist > 0 and hist_increasing:
            reason = f"Histogram positive ({hist}) and rising — bullish momentum"
            if crossover == "bullish_crossover":
                reason += " (fresh bullish crossover!)"
            return _log("MACD", vals, "BULLISH", reason)
        elif hist < 0 and not hist_increasing:
            reason = f"Histogram negative ({hist}) and falling — bearish momentum"
            if crossover == "bearish_crossover":
                reason += " (fresh bearish crossover!)"
            return _log("MACD", vals, "BEARISH", reason)
        else:
            return _log("MACD", vals, "NEUTRAL", f"Histogram={hist}, {'rising' if hist_increasing else 'falling'} — mixed signal")

    except Exception as e:
        return _log("MACD", {}, "NEUTRAL", f"Error: {e}")


def compute_stochastic(df: pd.DataFrame, k: int = 14, d: int = 3, smooth_k: int = 3) -> dict:
    """Stochastic %K/%D oscillator."""
    try:
        stoch = ta.stoch(df["High"], df["Low"], df["Close"], k=k, d=d, smooth_k=smooth_k)
        if stoch is None:
            return _log("Stochastic", {}, "NEUTRAL", "Insufficient data")

        k_val = round(float(stoch[f"STOCHk_{k}_{d}_{smooth_k}"].iloc[-1]), 2)
        d_val = round(float(stoch[f"STOCHd_{k}_{d}_{smooth_k}"].iloc[-1]), 2)

        vals = {"k_value": k_val, "d_value": d_val}

        if k_val < 20 and k_val > d_val:
            return _log("Stochastic", vals, "BULLISH", f"%K={k_val} crossing above %D={d_val} in oversold zone")
        elif k_val > 80 and k_val < d_val:
            return _log("Stochastic", vals, "BEARISH", f"%K={k_val} crossing below %D={d_val} in overbought zone")
        elif k_val < 20:
            return _log("Stochastic", vals, "NEUTRAL", f"Oversold (%K={k_val}) but no bullish crossover yet")
        elif k_val > 80:
            return _log("Stochastic", vals, "NEUTRAL", f"Overbought (%K={k_val}) but no bearish crossover yet")
        else:
            return _log("Stochastic", vals, "NEUTRAL", f"%K={k_val}, %D={d_val} — mid-range")

    except Exception as e:
        return _log("Stochastic", {}, "NEUTRAL", f"Error: {e}")


# ---------------------------------------------------------------------------
# 3. VOLUME
# ---------------------------------------------------------------------------

def compute_obv(df: pd.DataFrame) -> dict:
    """On-Balance Volume — checks divergence between price and volume trend."""
    try:
        close = df["Close"]
        volume = df["Volume"]
        obv = ta.obv(close, volume)
        if obv is None:
            return _log("OBV", {}, "NEUTRAL", "Insufficient data")

        lookback = min(10, len(obv) - 1)
        if lookback < 2:
            return _log("OBV", {}, "NEUTRAL", "Insufficient data for trend comparison")

        price_slope = (float(close.iloc[-1]) - float(close.iloc[-lookback])) / abs(float(close.iloc[-lookback])) if float(close.iloc[-lookback]) != 0 else 0
        obv_slope = (float(obv.iloc[-1]) - float(obv.iloc[-lookback])) / abs(float(obv.iloc[-lookback])) if float(obv.iloc[-lookback]) != 0 else 0

        vals = {
            "obv_current": int(obv.iloc[-1]),
            "price_trend": "UP" if price_slope > 0.01 else ("DOWN" if price_slope < -0.01 else "FLAT"),
            "obv_trend": "UP" if obv_slope > 0.01 else ("DOWN" if obv_slope < -0.01 else "FLAT"),
        }

        price_up = price_slope > 0.01
        price_down = price_slope < -0.01
        obv_up = obv_slope > 0.01
        obv_down = obv_slope < -0.01

        if price_up and obv_up:
            return _log("OBV", vals, "BULLISH", "Price and OBV both rising — strong buying pressure")
        elif price_up and obv_down:
            return _log("OBV", vals, "BEARISH", "Price rising but OBV falling — bearish divergence (distribution)")
        elif price_down and obv_up:
            return _log("OBV", vals, "BULLISH", "Price falling but OBV rising — bullish divergence (accumulation)")
        elif price_down and obv_down:
            return _log("OBV", vals, "BEARISH", "Price and OBV both falling — selling pressure")
        else:
            return _log("OBV", vals, "NEUTRAL", "No clear divergence or confirmation")

    except Exception as e:
        return _log("OBV", {}, "NEUTRAL", f"Error: {e}")


def compute_vwap(df: pd.DataFrame) -> dict:
    """Volume Weighted Average Price."""
    try:
        # VWAP requires a sorted, tz-consistent DatetimeIndex.
        # yfinance returns tz-aware, live bar is tz-naive — normalize all to naive.
        df_v = df.copy()
        idx = df_v.index
        if hasattr(idx, 'tz') and idx.tz is not None:
            idx = idx.tz_localize(None)
        else:
            idx = pd.DatetimeIndex([t.tz_localize(None) if hasattr(t, 'tz_localize') and t.tzinfo else t for t in idx])
        df_v.index = idx
        if not df_v.index.is_monotonic_increasing:
            df_v = df_v.sort_index()
        vwap = ta.vwap(df_v["High"], df_v["Low"], df_v["Close"], df_v["Volume"])
        if vwap is None:
            return _log("VWAP", {}, "NEUTRAL", "Insufficient data")

        vwap_val = round(float(vwap.iloc[-1]), 2)
        price = round(float(df["Close"].iloc[-1]), 2)
        pct = round((price - vwap_val) / vwap_val * 100, 2)

        vals = {"vwap": vwap_val, "price": price, "price_vs_vwap_pct": pct}

        if price > vwap_val:
            return _log("VWAP", vals, "BULLISH", f"Price ({price}) above VWAP ({vwap_val}) by {pct}% — buyers in control")
        else:
            return _log("VWAP", vals, "BEARISH", f"Price ({price}) below VWAP ({vwap_val}) by {pct}% — sellers in control")

    except Exception as e:
        return _log("VWAP", {}, "NEUTRAL", f"Error: {e}")


def compute_rvol(df: pd.DataFrame) -> dict:
    """Relative Volume — today vs 20-day average."""
    try:
        volume = df["Volume"]
        avg_vol = float(volume.rolling(20).mean().iloc[-1])
        curr_vol = float(volume.iloc[-1])
        rvol = round(curr_vol / avg_vol, 2) if avg_vol > 0 else 0
        price_change = float(df["Close"].iloc[-1]) - float(df["Close"].iloc[-2]) if len(df) > 1 else 0

        vals = {"rvol": rvol, "volume": int(curr_vol), "avg_volume_20d": int(avg_vol)}

        if rvol > 1.5 and price_change > 0:
            return _log("RVOL", vals, "BULLISH", f"Volume surge ({rvol}x avg) on up move — strong buying")
        elif rvol > 1.5 and price_change < 0:
            return _log("RVOL", vals, "BEARISH", f"Volume surge ({rvol}x avg) on down move — selling pressure")
        elif rvol < 0.5:
            return _log("RVOL", vals, "NEUTRAL", f"Very low volume ({rvol}x avg) — no conviction")
        else:
            return _log("RVOL", vals, "NEUTRAL", f"Normal volume ({rvol}x avg)")

    except Exception as e:
        return _log("RVOL", {}, "NEUTRAL", f"Error: {e}")


def compute_volume_profile(df: pd.DataFrame, num_bins: int = 20) -> dict:
    """Volume Profile — POC, VAH, VAL from price/volume distribution."""
    try:
        price_min = float(df["Low"].min())
        price_max = float(df["High"].max())
        if price_max - price_min < 0.01:
            return _log("Volume Profile", {}, "NEUTRAL", "Price range too narrow for volume profile")

        bin_edges = np.linspace(price_min, price_max, num_bins + 1)
        bin_volumes = np.zeros(num_bins)

        for _, row in df.iterrows():
            low, high, vol = float(row["Low"]), float(row["High"]), float(row["Volume"])
            for j in range(num_bins):
                bin_low, bin_high = bin_edges[j], bin_edges[j + 1]
                if high >= bin_low and low <= bin_high:
                    overlap = min(high, bin_high) - max(low, bin_low)
                    bar_range = high - low if high > low else 1
                    bin_volumes[j] += vol * (overlap / bar_range)

        poc_idx = int(np.argmax(bin_volumes))
        poc = round((bin_edges[poc_idx] + bin_edges[poc_idx + 1]) / 2, 2)

        # Value Area (70% of total volume)
        total_vol = bin_volumes.sum()
        target_vol = total_vol * 0.7
        va_indices = [poc_idx]
        cumulative = bin_volumes[poc_idx]
        lo, hi = poc_idx - 1, poc_idx + 1

        while cumulative < target_vol and (lo >= 0 or hi < num_bins):
            vol_lo = bin_volumes[lo] if lo >= 0 else 0
            vol_hi = bin_volumes[hi] if hi < num_bins else 0
            if vol_lo >= vol_hi and lo >= 0:
                va_indices.append(lo)
                cumulative += vol_lo
                lo -= 1
            elif hi < num_bins:
                va_indices.append(hi)
                cumulative += vol_hi
                hi += 1
            else:
                break

        val_level = round(bin_edges[min(va_indices)], 2)
        vah_level = round(bin_edges[max(va_indices) + 1], 2)
        price = round(float(df["Close"].iloc[-1]), 2)

        if price > vah_level:
            position = "above_value"
        elif price < val_level:
            position = "below_value"
        else:
            position = "in_value"

        vals = {"poc": poc, "vah": vah_level, "val": val_level, "price": price, "position": position}

        if position == "above_value":
            return _log("Volume Profile", vals, "BULLISH", f"Price ({price}) above Value Area High ({vah_level}) — breakout territory")
        elif position == "below_value":
            return _log("Volume Profile", vals, "BEARISH", f"Price ({price}) below Value Area Low ({val_level}) — breakdown territory")
        else:
            return _log("Volume Profile", vals, "NEUTRAL", f"Price ({price}) inside value area ({val_level}-{vah_level}) — fair value")

    except Exception as e:
        return _log("Volume Profile", {}, "NEUTRAL", f"Error: {e}")


# ---------------------------------------------------------------------------
# 4. VOLATILITY
# ---------------------------------------------------------------------------

def compute_bollinger(df: pd.DataFrame, length: int = 20, std: float = 2.0) -> dict:
    """Bollinger Bands with squeeze detection."""
    try:
        bbands = ta.bbands(df["Close"], length=length, std=std)
        if bbands is None:
            return _log("Bollinger Bands", {}, "NEUTRAL", "Insufficient data")

        # pandas-ta column names vary (BBU_20_2.0 or BBU_20_2) — find them dynamically
        cols = bbands.columns.tolist()
        bbu_col = [c for c in cols if c.startswith("BBU_")][0]
        bbm_col = [c for c in cols if c.startswith("BBM_")][0]
        bbl_col = [c for c in cols if c.startswith("BBL_")][0]
        bbb_col = [c for c in cols if c.startswith("BBB_")][0]
        bbp_col = [c for c in cols if c.startswith("BBP_")][0]

        upper = round(float(bbands[bbu_col].iloc[-1]), 2)
        middle = round(float(bbands[bbm_col].iloc[-1]), 2)
        lower = round(float(bbands[bbl_col].iloc[-1]), 2)
        bandwidth = round(float(bbands[bbb_col].iloc[-1]), 4)
        pct_b = round(float(bbands[bbp_col].iloc[-1]), 4)

        # Squeeze detection: current bandwidth < 80% of its 20-bar average
        bw_series = bbands[bbb_col]
        bw_avg = float(bw_series.rolling(20).mean().iloc[-1]) if len(bw_series) >= 20 else float(bw_series.mean())
        squeeze = bandwidth < 0.8 * bw_avg

        vals = {
            "upper": upper,
            "middle": middle,
            "lower": lower,
            "bandwidth": bandwidth,
            "pct_b": pct_b,
            "squeeze": squeeze,
        }

        if squeeze:
            return _log("Bollinger Bands", vals, "NEUTRAL", f"Bollinger squeeze detected (BW={bandwidth}) — expect breakout soon")
        elif pct_b < 0.2:
            return _log("Bollinger Bands", vals, "BULLISH", f"Price near lower band (%B={pct_b}) — oversold bounce zone")
        elif pct_b > 0.8:
            return _log("Bollinger Bands", vals, "BEARISH", f"Price near upper band (%B={pct_b}) — overbought, resistance ahead")
        else:
            return _log("Bollinger Bands", vals, "NEUTRAL", f"Price in mid-band range (%B={pct_b})")

    except Exception as e:
        return _log("Bollinger Bands", {}, "NEUTRAL", f"Error: {e}")


def compute_atr(df: pd.DataFrame, length: int = 14) -> dict:
    """ATR and ATR% of price — volatility context."""
    try:
        atr = ta.atr(df["High"], df["Low"], df["Close"], length=length)
        if atr is None:
            return _log("ATR", {}, "NEUTRAL", "Insufficient data")

        atr_val = round(float(atr.iloc[-1]), 2)
        price = round(float(df["Close"].iloc[-1]), 2)
        atr_pct = round(atr_val / price * 100, 2) if price > 0 else 0

        vals = {"atr": atr_val, "atr_pct": atr_pct, "price": price}

        if atr_pct > 5:
            reason = f"High volatility — ATR {atr_val} ({atr_pct}% of price). Wide stops needed."
        elif atr_pct > 3:
            reason = f"Moderate volatility — ATR {atr_val} ({atr_pct}% of price)."
        else:
            reason = f"Low volatility — ATR {atr_val} ({atr_pct}% of price). Tight range."

        return _log("ATR", vals, "NEUTRAL", reason)

    except Exception as e:
        return _log("ATR", {}, "NEUTRAL", f"Error: {e}")


# ---------------------------------------------------------------------------
# 5. LEVELS
# ---------------------------------------------------------------------------

def compute_fibonacci(df: pd.DataFrame) -> dict:
    """Fibonacci retracement from recent swing high/low."""
    try:
        swing_high = float(df["High"].max())
        swing_low = float(df["Low"].min())
        swing_high_idx = df["High"].idxmax()
        swing_low_idx = df["Low"].idxmin()
        price = round(float(df["Close"].iloc[-1]), 2)

        range_ = swing_high - swing_low
        if range_ < 0.01:
            return _log("Fibonacci", {}, "NEUTRAL", "Price range too narrow for Fibonacci")

        ratios = {"23.6%": 0.236, "38.2%": 0.382, "50.0%": 0.500, "61.8%": 0.618, "78.6%": 0.786}

        # Determine trend direction based on which extreme came last
        if swing_high_idx > swing_low_idx:
            trend = "uptrend_retracing"
            levels = {name: round(swing_high - ratio * range_, 2) for name, ratio in ratios.items()}
        else:
            trend = "downtrend_retracing"
            levels = {name: round(swing_low + ratio * range_, 2) for name, ratio in ratios.items()}

        # Find nearest level
        nearest_name = min(levels, key=lambda k: abs(levels[k] - price))
        nearest_val = levels[nearest_name]
        distance_pct = round(abs(price - nearest_val) / price * 100, 2)

        vals = {
            "swing_high": round(swing_high, 2),
            "swing_low": round(swing_low, 2),
            "trend": trend,
            "levels": levels,
            "nearest_level": f"{nearest_name} ({nearest_val})",
            "distance_to_nearest_pct": distance_pct,
            "price": price,
        }

        if trend == "uptrend_retracing":
            if price >= levels["38.2%"]:
                return _log("Fibonacci", vals, "BULLISH", f"Shallow retracement in uptrend — price near {nearest_name} ({nearest_val})")
            elif price >= levels["61.8%"]:
                return _log("Fibonacci", vals, "NEUTRAL", f"Deep retracement — testing {nearest_name} ({nearest_val})")
            else:
                return _log("Fibonacci", vals, "BEARISH", f"Below 61.8% retracement — uptrend may be broken")
        else:  # downtrend_retracing
            if price <= levels["38.2%"]:
                return _log("Fibonacci", vals, "BEARISH", f"Shallow bounce in downtrend — price near {nearest_name} ({nearest_val})")
            elif price <= levels["61.8%"]:
                return _log("Fibonacci", vals, "NEUTRAL", f"Deep bounce — testing {nearest_name} ({nearest_val})")
            else:
                return _log("Fibonacci", vals, "BULLISH", f"Above 61.8% bounce — downtrend may be reversing")

    except Exception as e:
        return _log("Fibonacci", {}, "NEUTRAL", f"Error: {e}")


def compute_pivot_points(df: pd.DataFrame) -> dict:
    """Classic Pivot Points from previous day's H/L/C."""
    try:
        if len(df) < 2:
            return _log("Pivot Points", {}, "NEUTRAL", "Need at least 2 bars")

        prev = df.iloc[-2]
        h, l, c = float(prev["High"]), float(prev["Low"]), float(prev["Close"])
        price = round(float(df["Close"].iloc[-1]), 2)

        pp = round((h + l + c) / 3, 2)
        r1 = round(2 * pp - l, 2)
        r2 = round(pp + (h - l), 2)
        r3 = round(h + 2 * (pp - l), 2)
        s1 = round(2 * pp - h, 2)
        s2 = round(pp - (h - l), 2)
        s3 = round(l - 2 * (h - pp), 2)

        # Determine position
        if price > r2:
            position = f"above R2 ({r2})"
        elif price > r1:
            position = f"between R1 ({r1}) and R2 ({r2})"
        elif price > pp:
            position = f"between PP ({pp}) and R1 ({r1})"
        elif price > s1:
            position = f"between S1 ({s1}) and PP ({pp})"
        elif price > s2:
            position = f"between S2 ({s2}) and S1 ({s1})"
        else:
            position = f"below S2 ({s2})"

        vals = {"pp": pp, "r1": r1, "r2": r2, "r3": r3, "s1": s1, "s2": s2, "s3": s3, "price": price, "position": position}

        pp_threshold = pp * 0.005  # 0.5%
        if price > pp + pp_threshold:
            return _log("Pivot Points", vals, "BULLISH", f"Price ({price}) above pivot ({pp}) — {position}")
        elif price < pp - pp_threshold:
            return _log("Pivot Points", vals, "BEARISH", f"Price ({price}) below pivot ({pp}) — {position}")
        else:
            return _log("Pivot Points", vals, "NEUTRAL", f"Price ({price}) near pivot ({pp})")

    except Exception as e:
        return _log("Pivot Points", {}, "NEUTRAL", f"Error: {e}")


# ---------------------------------------------------------------------------
# 6. PATTERNS
# ---------------------------------------------------------------------------

def compute_candlestick_patterns(df: pd.DataFrame) -> dict:
    """Detect common candlestick patterns in the last 5 bars."""
    try:
        if len(df) < 5:
            return _log("Candlestick Patterns", {}, "NEUTRAL", "Need at least 5 bars")

        patterns_found = []
        last5 = df.iloc[-5:]

        def body(row):
            return abs(float(row["Close"]) - float(row["Open"]))

        def bar_range(row):
            return float(row["High"]) - float(row["Low"])

        def is_bullish(row):
            return float(row["Close"]) > float(row["Open"])

        def upper_shadow(row):
            return float(row["High"]) - max(float(row["Close"]), float(row["Open"]))

        def lower_shadow(row):
            return min(float(row["Close"]), float(row["Open"])) - float(row["Low"])

        # Last bar
        curr = last5.iloc[-1]
        prev = last5.iloc[-2]
        br = bar_range(curr)

        if br > 0:
            # Doji — body < 10% of range
            if body(curr) < 0.1 * br:
                patterns_found.append("Doji")

            # Hammer — lower shadow >= 2x body, body in upper third
            if lower_shadow(curr) >= 2 * body(curr) and upper_shadow(curr) < body(curr) and body(curr) > 0:
                patterns_found.append("Hammer (bullish)")

            # Inverted Hammer / Shooting Star
            if upper_shadow(curr) >= 2 * body(curr) and lower_shadow(curr) < body(curr) and body(curr) > 0:
                if not is_bullish(curr):
                    patterns_found.append("Shooting Star (bearish)")
                else:
                    patterns_found.append("Inverted Hammer (bullish)")

        # Engulfing (2-bar)
        if body(curr) > 0 and body(prev) > 0:
            if is_bullish(curr) and not is_bullish(prev):
                if float(curr["Close"]) > float(prev["Open"]) and float(curr["Open"]) < float(prev["Close"]):
                    patterns_found.append("Bullish Engulfing")
            elif not is_bullish(curr) and is_bullish(prev):
                if float(curr["Open"]) > float(prev["Close"]) and float(curr["Close"]) < float(prev["Open"]):
                    patterns_found.append("Bearish Engulfing")

        # Morning/Evening Star (3-bar)
        if len(last5) >= 3:
            bar1, bar2, bar3 = last5.iloc[-3], last5.iloc[-2], last5.iloc[-1]
            b1_body = body(bar1)
            b2_body = body(bar2)
            b3_body = body(bar3)

            if b1_body > 0 and b3_body > 0:
                # Morning Star: big bearish + small body + big bullish
                if not is_bullish(bar1) and b1_body > 2 * b2_body and is_bullish(bar3) and b3_body > 2 * b2_body:
                    patterns_found.append("Morning Star (bullish)")
                # Evening Star: big bullish + small body + big bearish
                elif is_bullish(bar1) and b1_body > 2 * b2_body and not is_bullish(bar3) and b3_body > 2 * b2_body:
                    patterns_found.append("Evening Star (bearish)")

        vals = {"patterns_detected": patterns_found if patterns_found else ["None"]}

        bullish = [p for p in patterns_found if "bullish" in p.lower() or "Hammer" in p]
        bearish = [p for p in patterns_found if "bearish" in p.lower() or "Shooting" in p]

        if bullish and not bearish:
            return _log("Candlestick Patterns", vals, "BULLISH", f"Bullish patterns: {', '.join(bullish)}")
        elif bearish and not bullish:
            return _log("Candlestick Patterns", vals, "BEARISH", f"Bearish patterns: {', '.join(bearish)}")
        elif patterns_found and patterns_found != ["None"]:
            return _log("Candlestick Patterns", vals, "NEUTRAL", f"Mixed patterns: {', '.join(patterns_found)}")
        else:
            return _log("Candlestick Patterns", vals, "NEUTRAL", "No significant patterns in last 5 bars")

    except Exception as e:
        return _log("Candlestick Patterns", {}, "NEUTRAL", f"Error: {e}")


def compute_gap_analysis(df: pd.DataFrame, live_bar: dict | None = None) -> dict:
    """Gap analysis — today's open vs yesterday's close."""
    try:
        if live_bar and "open" in live_bar and "ldcp" in live_bar:
            today_open = float(live_bar["open"])
            yesterday_close = float(live_bar["ldcp"])
        elif len(df) >= 2:
            today_open = float(df["Open"].iloc[-1])
            yesterday_close = float(df["Close"].iloc[-2])
        else:
            return _log("Gap Analysis", {}, "NEUTRAL", "Insufficient data")

        gap = round(today_open - yesterday_close, 2)
        gap_pct = round(gap / yesterday_close * 100, 2) if yesterday_close > 0 else 0

        vals = {"gap": gap, "gap_pct": gap_pct, "today_open": today_open, "yesterday_close": yesterday_close}

        if gap_pct > 1:
            return _log("Gap Analysis", vals, "BULLISH", f"Gap up +{gap_pct}% (opened {today_open} vs prev close {yesterday_close})")
        elif gap_pct < -1:
            return _log("Gap Analysis", vals, "BEARISH", f"Gap down {gap_pct}% (opened {today_open} vs prev close {yesterday_close})")
        else:
            return _log("Gap Analysis", vals, "NEUTRAL", f"No significant gap ({gap_pct}%)")

    except Exception as e:
        return _log("Gap Analysis", {}, "NEUTRAL", f"Error: {e}")


# ---------------------------------------------------------------------------
# 7. META
# ---------------------------------------------------------------------------

def compute_confluence(log_entries: list[dict]) -> dict:
    """Count bullish vs bearish signals across all techniques."""
    bullish = sum(1 for e in log_entries if e["signal"] == "BULLISH")
    bearish = sum(1 for e in log_entries if e["signal"] == "BEARISH")
    neutral = sum(1 for e in log_entries if e["signal"] == "NEUTRAL")
    total = len(log_entries)

    vals = {
        "bullish_count": bullish,
        "bearish_count": bearish,
        "neutral_count": neutral,
        "total": total,
        "score_text": f"{bullish}/{total} bullish, {bearish}/{total} bearish",
    }

    if bullish > 0 and bullish >= 2 * bearish:
        return _log("Confluence", vals, "BULLISH", f"Strong bullish confluence — {bullish} bullish vs {bearish} bearish signals")
    elif bearish > 0 and bearish >= 2 * bullish:
        return _log("Confluence", vals, "BEARISH", f"Strong bearish confluence — {bearish} bearish vs {bullish} bullish signals")
    else:
        return _log("Confluence", vals, "NEUTRAL", f"Mixed signals — {bullish} bullish, {bearish} bearish, {neutral} neutral")


# ---------------------------------------------------------------------------
# MASTER FUNCTION
# ---------------------------------------------------------------------------

def run_deep_analysis(df: pd.DataFrame, live_bar: dict | None = None) -> list[dict]:
    """Run ALL 17 techniques + confluence. Returns list of 18 log dicts."""
    logs = [
        # Core Trend
        compute_renko(df),
        compute_point_and_figure(df),
        compute_ema_trend(df),
        compute_adx(df),
        # Momentum
        compute_rsi(df),
        compute_macd(df),
        compute_stochastic(df),
        # Volume
        compute_obv(df),
        compute_vwap(df),
        compute_rvol(df),
        compute_volume_profile(df),
        # Volatility
        compute_bollinger(df),
        compute_atr(df),
        # Levels
        compute_fibonacci(df),
        compute_pivot_points(df),
        # Patterns
        compute_candlestick_patterns(df),
        compute_gap_analysis(df, live_bar),
    ]
    # Confluence is computed on the 17 technique results
    logs.append(compute_confluence(logs))
    return logs
