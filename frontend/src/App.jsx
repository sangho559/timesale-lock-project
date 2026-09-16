import { useEffect, useRef, useState } from "react";
import { LOCK_MODES, fetchProduct, resetStock, createProduct, placeOrder } from "./api";
import "./App.css";

const PRODUCT_ID = 1;
const INITIAL_STOCK = 20;

function StatusBadge({ status }) {
  const map = {
    success: { label: "성공", cls: "badge success" },
    out_of_stock: { label: "재고 부족", cls: "badge muted" },
    retry_exhausted: { label: "재시도 초과", cls: "badge danger" },
    error: { label: "요청 실패", cls: "badge danger" },
  };
  const s = map[status] || { label: status, cls: "badge muted" };
  return <span className={s.cls}>{s.label}</span>;
}

export default function App() {
  const [product, setProduct] = useState(null);
  const [modeKey, setModeKey] = useState("no-lock");
  const [log, setLog] = useState([]);
  const [busy, setBusy] = useState(false);
  const [rushCount, setRushCount] = useState(30);
  const [connError, setConnError] = useState(false);
  const logEndRef = useRef(null);

  const mode = LOCK_MODES.find((m) => m.key === modeKey);

  async function loadProduct() {
    try {
      const p = await fetchProduct(PRODUCT_ID);
      setProduct(p);
      setConnError(false);
    } catch (e) {
      setConnError(true);
    }
  }

  async function initProduct() {
    try {
      try {
        await fetchProduct(PRODUCT_ID);
        await resetStock(PRODUCT_ID, INITIAL_STOCK);
      } catch (notFound) {
        // 상품이 아예 없는 최초 실행(DB 초기 상태) -> 새로 생성
        await createProduct({
          name: "타임세일 시뮬레이션 상품",
          stock: INITIAL_STOCK,
          price: 9900,
        });
      }
      await loadProduct();
    } catch (e) {
      setConnError(true);
    }
  }

  useEffect(() => {
    initProduct();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function pushLog(entries) {
    setLog((prev) => [...entries, ...prev].slice(0, 200));
  }

  async function handleSingleOrder() {
    setBusy(true);
    const userId = `user-${Date.now()}`;
    const startedAt = new Date().toLocaleTimeString("ko-KR", { hour12: false });
    try {
      const result = await placeOrder(mode.endpoint, PRODUCT_ID, userId);
      pushLog([{ ...result, userId, time: startedAt, mode: mode.key }]);
      await loadProduct();
    } catch (e) {
      pushLog([{ status: "error", userId, time: startedAt, mode: mode.key, message: "네트워크 오류" }]);
    }
    setBusy(false);
  }

  async function handleRush() {
    setBusy(true);
    const time = new Date().toLocaleTimeString("ko-KR", { hour12: false });
    const requests = Array.from({ length: rushCount }, (_, i) =>
      placeOrder(mode.endpoint, PRODUCT_ID, `rush-${Date.now()}-${i}`)
        .then((r) => ({ ...r, userId: `rush-${i}`, time, mode: mode.key }))
        .catch(() => ({ status: "error", userId: `rush-${i}`, time, mode: mode.key }))
    );
    const results = await Promise.all(requests);
    pushLog(results);
    await loadProduct();
    setBusy(false);
  }

  async function handleReset() {
    setBusy(true);
    await initProduct();
    setLog([]);
    setBusy(false);
  }

  const stockRatio = product ? Math.max(product.stock, 0) / INITIAL_STOCK : 0;

  return (
    <div className="page">
      <header className="hero">
        <p className="hero-eyebrow-free">동시성 제어 비교 데모</p>
        <h1>
          같은 재고, 다른 락 — <span className="accent">누가 진짜로 100개만 팔까</span>
        </h1>
        <p className="hero-sub">
          같은 타임세일 API를 락 없음 / 비관적 락 / 낙관적 락 세 가지 방식으로 구현했습니다.
          아래에서 방식을 바꿔가며 혼자 눌러보거나, 여러 명이 동시에 몰리는 상황을 재현해보세요.
        </p>
      </header>

      {connError && (
        <div className="conn-error">
          백엔드(localhost:8000)에 연결할 수 없습니다. <code>uvicorn app.main:app --reload</code> 로 서버를 먼저 실행해주세요.
        </div>
      )}

      <div className="layout">
        <section className="panel product-panel">
          <div className="panel-label">TIMESALE ITEM</div>
          <h2 className="product-name">{product?.name || "타임세일 시뮬레이션 상품"}</h2>
          <div className="price">
            {product ? Number(product.price).toLocaleString("ko-KR") : "—"}<span className="won">원</span>
          </div>

          <div className="stock-block">
            <div className="stock-row">
              <span>남은 재고</span>
              <span className="stock-number">
                {product ? Math.max(product.stock, 0) : "—"} / {INITIAL_STOCK}
              </span>
            </div>
            <div className="stock-bar-track">
              <div
                className="stock-bar-fill"
                style={{
                  width: `${Math.min(Math.max(stockRatio, 0), 1) * 100}%`,
                  background:
                    stockRatio <= 0
                      ? "#3a3f47"
                      : stockRatio < 0.3
                      ? "#ff5a44"
                      : "#ffb020",
                }}
              />
            </div>
          </div>

          <button className="btn-reset" onClick={handleReset} disabled={busy}>
            재고 {INITIAL_STOCK}개로 초기화 + 로그 지우기
          </button>
        </section>

        <section className="panel control-panel">
          <div className="panel-label">LOCK MODE</div>
          <div className="mode-toggle">
            {LOCK_MODES.map((m) => (
              <button
                key={m.key}
                className={`mode-btn tone-${m.tone} ${modeKey === m.key ? "active" : ""}`}
                onClick={() => setModeKey(m.key)}
              >
                <span className="mode-label">{m.label}</span>
                <span className="mode-sub">{m.sub}</span>
              </button>
            ))}
          </div>
          <p className="mode-desc">{mode.desc}</p>

          <div className="action-row">
            <button className="btn-primary" onClick={handleSingleOrder} disabled={busy}>
              1명 구매하기
            </button>
          </div>

          <div className="rush-block">
            <div className="rush-row">
              <label htmlFor="rush">동시에 몰리는 인원</label>
              <input
                id="rush"
                type="number"
                min={2}
                max={300}
                value={rushCount}
                onChange={(e) => setRushCount(Number(e.target.value))}
              />
              <span>명</span>
            </div>
            <button className="btn-rush" onClick={handleRush} disabled={busy}>
              지금 동시에 {rushCount}명 구매 시도 →
            </button>
          </div>
        </section>
      </div>

      <section className="panel log-panel">
        <div className="panel-label">ORDER LOG (최신순)</div>
        {log.length === 0 ? (
          <p className="log-empty">아직 요청 기록이 없습니다. 위에서 구매를 시도해보세요.</p>
        ) : (
          <div className="log-list">
            {log.map((entry, i) => (
              <div className="log-row" key={i}>
                <span className="log-time">{entry.time}</span>
                <span className={`log-mode mode-${entry.mode}`}>
                  {LOCK_MODES.find((m) => m.key === entry.mode)?.label}
                </span>
                <StatusBadge status={entry.status} />
                <span className="log-detail">
                  {entry.remaining_stock !== undefined && entry.remaining_stock !== null
                    ? `남은 재고 ${entry.remaining_stock}`
                    : ""}
                  {entry.retry_count > 0 ? ` · 재시도 ${entry.retry_count}회` : ""}
                  {entry.duration_ms ? ` · ${Number(entry.duration_ms).toFixed(1)}ms` : ""}
                </span>
              </div>
            ))}
          </div>
        )}
        <div ref={logEndRef} />
      </section>

      <footer className="footer-note">
        선착순 타임세일 &amp; 재고 차감 API — 비관적 락 vs 낙관적 락 동시성 제어 비교 포트폴리오 데모
      </footer>
    </div>
  );
}
