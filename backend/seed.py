import json
import time
import uuid
from database import get_turso, init_db, sync_strategies_to_local

TEMPLATES = [
    {
        "template_id": "ma_crossover",
        "name": "雙均線交叉",
        "description": "快線穿越慢線時做多/做空，支援 SMA/EMA 與成交量過濾",
        "parameters": [
            {"name": "fast_period", "type": "integer", "min": 5, "max": 50, "step": 1, "default": 10},
            {"name": "slow_period", "type": "integer", "min": 20, "max": 200, "step": 1, "default": 50},
            {"name": "ma_type", "type": "categorical", "options": ["SMA", "EMA"], "default": "SMA"},
            {"name": "use_volume_filter", "type": "boolean", "default": False, "controls": ["volume_period", "volume_threshold"]},
            {"name": "volume_period", "type": "integer", "min": 5, "max": 30, "step": 1, "default": 20},
            {"name": "volume_threshold", "type": "continuous", "min": 1.0, "max": 3.0, "scale": "linear", "default": 1.5},
            {"name": "stop_loss_pct", "type": "continuous", "min": 0.005, "max": 0.1, "scale": "linear", "default": 0.03},
            {"name": "take_profit_pct", "type": "continuous", "min": 0.01, "max": 0.3, "scale": "linear", "default": 0.06},
        ],
        "constraints": [
            {"type": "ordering", "params": ["fast_period", "slow_period"], "relation": "less_than", "repair": "clamp_upper"},
            {"type": "conditional", "controller": "use_volume_filter", "active_when": True, "controlled_params": ["volume_period", "volume_threshold"]},
            {"type": "ordering", "params": ["stop_loss_pct", "take_profit_pct"], "relation": "less_than", "repair": "clamp_upper"},
        ],
    },
    {
        "template_id": "rsi_mean_reversion",
        "name": "RSI 超買超賣",
        "description": "RSI 跌破超賣做多、突破超買做空，支援確認 K 線數與動態止損",
        "parameters": [
            {"name": "rsi_period", "type": "integer", "min": 5, "max": 30, "step": 1, "default": 14},
            {"name": "oversold_threshold", "type": "integer", "min": 15, "max": 40, "step": 1, "default": 30},
            {"name": "overbought_threshold", "type": "integer", "min": 60, "max": 85, "step": 1, "default": 70},
            {"name": "confirmation_bars", "type": "integer", "min": 1, "max": 5, "step": 1, "default": 1},
            {"name": "stop_loss_mode", "type": "categorical", "options": ["fixed_pct", "atr_multiple"], "default": "fixed_pct"},
            {"name": "stop_loss_pct", "type": "continuous", "min": 0.005, "max": 0.1, "scale": "linear", "default": 0.03},
            {"name": "atr_period", "type": "integer", "min": 5, "max": 30, "step": 1, "default": 14},
            {"name": "atr_multiplier", "type": "continuous", "min": 1.0, "max": 5.0, "scale": "linear", "default": 2.0},
            {"name": "take_profit_rsi", "type": "integer", "min": 45, "max": 60, "step": 1, "default": 50},
        ],
        "constraints": [
            {"type": "ordering", "params": ["oversold_threshold", "overbought_threshold"], "relation": "less_than", "repair": "clamp_upper"},
            {"type": "categorical_group", "controller": "stop_loss_mode", "groups": {"fixed_pct": ["stop_loss_pct"], "atr_multiple": ["atr_period", "atr_multiplier"]}, "common_params": ["rsi_period", "oversold_threshold", "overbought_threshold", "confirmation_bars", "take_profit_rsi"]},
        ],
    },
    {
        "template_id": "bollinger_breakout",
        "name": "布林通道突破",
        "description": "收盤突破布林通道上下軌進場，支援擠壓過濾與多種出場模式",
        "parameters": [
            {"name": "bb_period", "type": "integer", "min": 10, "max": 50, "step": 1, "default": 20},
            {"name": "bb_std", "type": "continuous", "min": 1.0, "max": 4.0, "scale": "linear", "default": 2.0},
            {"name": "use_squeeze_filter", "type": "boolean", "default": True, "controls": ["squeeze_period", "squeeze_threshold"]},
            {"name": "squeeze_period", "type": "integer", "min": 10, "max": 50, "step": 1, "default": 20},
            {"name": "squeeze_threshold", "type": "continuous", "min": 0.3, "max": 0.9, "scale": "linear", "default": 0.6},
            {"name": "exit_mode", "type": "categorical", "options": ["midline", "fixed"], "default": "midline"},
            {"name": "stop_loss_pct", "type": "continuous", "min": 0.005, "max": 0.15, "scale": "linear", "default": 0.05},
            {"name": "take_profit_pct", "type": "continuous", "min": 0.01, "max": 0.3, "scale": "linear", "default": 0.1},
            {"name": "midline_exit_buffer", "type": "continuous", "min": 0.0, "max": 0.02, "scale": "linear", "default": 0.005},
        ],
        "constraints": [
            {"type": "conditional", "controller": "use_squeeze_filter", "active_when": True, "controlled_params": ["squeeze_period", "squeeze_threshold"]},
            {"type": "categorical_group", "controller": "exit_mode", "groups": {"fixed": ["stop_loss_pct", "take_profit_pct"], "midline": ["midline_exit_buffer"]}, "common_params": ["bb_period", "bb_std", "use_squeeze_filter", "squeeze_period", "squeeze_threshold"]},
            {"type": "ordering", "params": ["stop_loss_pct", "take_profit_pct"], "relation": "less_than", "repair": "clamp_upper"},
        ],
    },
    {
        "template_id": "omniscient_paradox",
        "name": "Omniscient Paradox（槓桿ETF動量輪換）",
        "description": "每日在8支槓桿ETF間輪換，使用多周期動量評分（ROC9/21/63）+ 波動率調整 + 趨勢過濾（SMA50）+ RSI懲罰，並以SPY SMA200作為大盤趨勢濾網。持倉集中單一資產，波動率目標化配置。",
        "parameters": [
            {"type": "integer",    "name": "roc_fast_period",       "label": "短期ROC周期",  "min": 5,   "max": 21,  "default": 9,   "step": 1},
            {"type": "integer",    "name": "roc_med_period",        "label": "中期ROC周期",  "min": 10,  "max": 40,  "default": 21,  "step": 1},
            {"type": "integer",    "name": "roc_slow_period",       "label": "長期ROC周期",  "min": 40,  "max": 120, "default": 63,  "step": 1},
            {"type": "integer",    "name": "vol_period",            "label": "波動率周期",   "min": 10,  "max": 30,  "default": 21,  "step": 1},
            {"type": "integer",    "name": "rsi_period",            "label": "RSI周期",      "min": 7,   "max": 21,  "default": 14,  "step": 1},
            {"type": "integer",    "name": "sma_period",            "label": "SMA周期",      "min": 20,  "max": 100, "default": 50,  "step": 1},
            {"type": "integer",    "name": "spy_sma_period",        "label": "SPY趨勢SMA",   "min": 100, "max": 300, "default": 200, "step": 10},
            {"type": "integer",    "name": "lookback_vol",          "label": "波動率回看",   "min": 10,  "max": 40,  "default": 20,  "step": 1},
            {"type": "continuous", "name": "fast_weight",           "label": "短ROC權重",    "min": 0.2, "max": 0.7, "default": 0.5},
            {"type": "continuous", "name": "med_weight",            "label": "中ROC權重",    "min": 0.1, "max": 0.5, "default": 0.3},
            {"type": "continuous", "name": "slow_weight",           "label": "長ROC權重",    "min": 0.05,"max": 0.4, "default": 0.2},
            {"type": "continuous", "name": "target_vol",            "label": "目標波動率",   "min": 0.4, "max": 1.0, "default": 0.8},
            {"type": "continuous", "name": "confidence_threshold",  "label": "切換信心門檻",  "min": 0.0, "max": 0.3, "default": 0.1},
            {"type": "continuous", "name": "rsi_overbought",        "label": "RSI超買門檻",  "min": 70.0,"max": 95.0,"default": 85.0},
            {"type": "continuous", "name": "rsi_oversold",          "label": "RSI超賣門檻",  "min": 15.0,"max": 40.0,"default": 30.0},
            {"type": "continuous", "name": "rsi_penalty",           "label": "RSI懲罰係數",  "min": 0.5, "max": 1.0, "default": 0.9},
        ],
        "constraints": [],
    },
    {
        "template_id": "macd_momentum",
        "name": "MACD 動能",
        "description": "MACD 穿越信號線配合柱狀圖確認，支援趨勢過濾",
        "parameters": [
            {"name": "fast_ema", "type": "integer", "min": 5, "max": 20, "step": 1, "default": 12},
            {"name": "slow_ema", "type": "integer", "min": 15, "max": 50, "step": 1, "default": 26},
            {"name": "signal_period", "type": "integer", "min": 5, "max": 15, "step": 1, "default": 9},
            {"name": "histogram_confirm_bars", "type": "integer", "min": 1, "max": 4, "step": 1, "default": 1},
            {"name": "require_macd_positive", "type": "boolean", "default": True, "controls": []},
            {"name": "use_trend_filter", "type": "boolean", "default": False, "controls": ["trend_ma_period", "trend_ma_type"]},
            {"name": "trend_ma_period", "type": "integer", "min": 50, "max": 200, "step": 5, "default": 100},
            {"name": "trend_ma_type", "type": "categorical", "options": ["SMA", "EMA"], "default": "SMA"},
            {"name": "stop_loss_pct", "type": "continuous", "min": 0.005, "max": 0.1, "scale": "linear", "default": 0.03},
            {"name": "take_profit_pct", "type": "continuous", "min": 0.01, "max": 0.25, "scale": "linear", "default": 0.09},
        ],
        "constraints": [
            {"type": "ordering", "params": ["fast_ema", "slow_ema"], "relation": "less_than", "repair": "clamp_upper"},
            {"type": "conditional", "controller": "use_trend_filter", "active_when": True, "controlled_params": ["trend_ma_period", "trend_ma_type"]},
            {"type": "ordering", "params": ["stop_loss_pct", "take_profit_pct"], "relation": "less_than", "repair": "clamp_upper"},
        ],
    },
]


def seed_templates():
    init_db()
    try:
        t = get_turso()
        _seed_into(t)
        sync_strategies_to_local()
    except RuntimeError:
        from database import get_db as _get_local
        local = _get_local()
        _seed_into(local)
        local.commit()
        local.close()


def _seed_into(dest):
    now = int(time.time())
    existing_ids = {
        r[0] for r in dest.execute(
            "SELECT template_id FROM strategy_configs WHERE is_template = 1"
        ).fetchall()
    }
    for tmpl in TEMPLATES:
        if tmpl["template_id"] in existing_ids:
            continue
        config_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"template/{tmpl['template_id']}"))
        dest.execute(
            """INSERT OR IGNORE INTO strategy_configs
               (config_id, name, description, template_id, is_template, is_locked,
                parameters_json, constraints_json, created_at, updated_at)
               VALUES (?, ?, ?, ?, 1, 0, ?, ?, ?, ?)""",
            (
                config_id,
                tmpl["name"],
                tmpl["description"],
                tmpl["template_id"],
                json.dumps(tmpl["parameters"]),
                json.dumps(tmpl["constraints"]),
                now,
                now,
            ),
        )
