# QuantGene Evolution Platform - 系統架構與 Claude 開發指引

## 1. 高階系統架構總覽 (System Architecture Overview)

本系統採模組化設計，核心邏輯與 UI 介面完全解耦，確保回測與演化運算的效能與可靠性。

### 核心技術棧
- **前端**: React 18 + Vite, TypeScript, shadcn/ui, Tailwind CSS, Plotly.js (3D 視覺化).
- **後端運算**: Python 3.10+, Pandas, NumPy, multiprocessing.
- **資料儲存**: SQLite (WAL 模式).
- **行情來源**: Binance 公開 WebSocket/REST API.

### 模組交互流向
1. **策略定義**: 使用者透過 UI 定義策略與參數空間（Module 7 & 2）。
2. **演化調度**: 演化引擎（Module 4）協調參數採樣、並行回測（Module 1）與適應度評分（Module 3）。
3. **數據持久化**: 過程數據即時寫入 SQLite（Module 5）並透過 WebSocket 推送至前端。
4. **實盤驗證**: 優化後的策略部署至 Paper Trading（Module 8）進行模擬交易。

---

## 2. Claude Code 專用精簡上下文 (Claude Context Prompt)

**複製以下內容至 Claude Code 的 Session 中，可有效減少 Token 消耗並防止幻覺：**

> ### [System Context: QuantGene Platform]
> 你是量化開發專家，協助開發 QuantGene 遺傳演算法平台。
>
> **核心約束：**
> 1. **技術棧**: React/TS (前端), Python/Pandas (後端), SQLite (資料庫)。
> 2. **並行處理**: 使用 Python `multiprocessing`，OHLCV 資料採共享記憶體模式。
> 3. **無前瞻偏差**: 信號計算嚴格禁止使用未來 K 線。
> 4. **模組邊界**:
>    - Module 1 (Backtest): 僅執行回測，不涉及演化或 DB。
>    - Module 2 (Param): 處理參數 sample/repair/encode，不涉及回測。
>    - Module 3 (Fitness): 處理 OOS/Pareto 排名，不涉及策略邏輯。
>    - Module 5 (Storage): 純 SQLite 讀寫，不主動運算。
> 5. **開發規範**: 每次完成模組後需產出介面文檔（.md），詳列 API 與資料結構。
> 6. **安全**: 僅使用 Binance 公開 API，不處理真實資金。

---

## 3. 開發規範與介面文檔規則 (Interface Documentation Rules)

為了確保跨模組串接的順暢，請遵守以下規則：

1. **獨立介面檔**: 每個模組實作完成後，必須在 `docs/interfaces/` 目錄下建立 `{Module_Name}_Interface.md`。
2. **內容要求**:
   - **Exported Functions**: 函式名稱、輸入參數型別、輸出格式。
   - **Data Schemas**: JSON 或字典的 Key 定義。
   - **Error Handling**: 模組可能拋出的錯誤類型。
3. **跨模組參考**: 後續模組開發時，應優先閱讀對應介面檔，而非原始碼。
