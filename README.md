# QuantGene Evolution Platform

基因演化策略回測平台 — 整合回測、演化優化、模擬交易、實盤交易。

## 目錄結構

```
├── backend/              # FastAPI 後端
│   ├── backtest/         # 回測引擎
│   ├── evolution/        # 基因演化引擎
│   ├── paper_trading/    # 模擬交易
│   ├── live_trading/     # 實盤交易（Alpaca）
│   ├── routes/           # REST API 路由
│   └── tests/            # 單元測試
├── frontend/             # React + Vite 前端
│   └── src/
│       ├── components/   # React 組件
│       ├── types/        # TypeScript 型別
│       ├── hooks/        # React Hooks
│       ├── lib/          # 工具函式
│       └── store/        # Zustand 狀態管理
├── database.py           # 資料庫連線（轉發至 backend/database.py）
├── data_fetcher.py       # 行情資料下載
├── docker-compose.yml    # Docker 部署
└── pyproject.toml        # Python 工具設定
```

## 快速開始

### 前置需求

- Node.js >= 22
- Python >= 3.11
- Turso DB（可選，無則使用本地 SQLite）

### 後端

```bash
cd backend
pip install -r requirements.txt
cp .env.example .env  # 編輯環境變數
uvicorn main:app --reload --port 8000
```

### 前端

```bash
cd frontend
npm install
npm run dev  # http://localhost:5173
```

### Docker

```bash
docker compose up --build
# 前端 http://localhost:3000
# 後端 http://localhost:8000
# API 文件 http://localhost:8000/docs
```

## 環境變數

參見 `.env.example`，主要包含：

| 變數 | 說明 |
|------|------|
| `TURSO_URL` / `TURSO_TOKEN` | Turso 遠端資料庫 |
| `ALPACA_API_KEY` / `ALPACA_SECRET_KEY` | Alpaca 實盤交易 |
| `RENDER_PAPER_URL` | Render 上的 paper service URL |

## 開發

```bash
# 後端 lint
cd backend && ruff check .

# 前端 lint + typecheck
cd frontend && npm run lint && npm run build
```
