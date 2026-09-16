"""
동시 요청 시뮬레이션 스크립트

사용법:
    python simulate.py

재고 N개짜리 상품에 대해 M명이 동시에 1개씩 구매를 시도했을 때,
no-lock / pessimistic / optimistic 3가지 방식 각각에 대해
- 정합성 (재고가 음수가 되거나, 실제 성공 건수와 차감량이 안 맞는지)
- TPS (전체 처리 시간 대비 처리량)
- 실패/재시도 횟수
- 응답시간 분포 (p50/p95/p99)
를 측정하고 results/raw_results.json 으로 저장합니다.
(그래프 생성은 3단계 analyze.py에서 raw_results.json을 읽어 처리)
"""
import concurrent.futures
import json
import time
import statistics
from pathlib import Path

import httpx

BASE_URL = "http://localhost:8000"

# ---- 실험 설정 -------------------------------------------------------
INITIAL_STOCK = 100     # 상품 재고
CONCURRENT_USERS = 500  # 동시 구매 시도 인원
MAX_WORKERS = 50         # 동시 커넥션 수 (스레드풀 크기)
PRODUCT_ID = 1
# ----------------------------------------------------------------------

RESULTS_DIR = Path(__file__).resolve().parent.parent / "results"
RESULTS_DIR.mkdir(exist_ok=True)


def ensure_product():
    """상품이 없으면 생성하고, 있으면 재고만 초기화."""
    with httpx.Client(timeout=30) as client:
        r = client.get(f"{BASE_URL}/product/{PRODUCT_ID}")
        if r.status_code == 404:
            r = client.post(
                f"{BASE_URL}/product/",
                json={"name": "타임세일 시뮬레이션 상품", "stock": INITIAL_STOCK, "price": 9900},
            )
            r.raise_for_status()
        else:
            reset_stock()


def reset_stock():
    with httpx.Client(timeout=30) as client:
        r = client.post(
            f"{BASE_URL}/product/{PRODUCT_ID}/reset-stock",
            params={"stock": INITIAL_STOCK},
        )
        r.raise_for_status()


def get_stock():
    with httpx.Client(timeout=30) as client:
        r = client.get(f"{BASE_URL}/product/{PRODUCT_ID}")
        r.raise_for_status()
        return r.json()["stock"]


def single_order(endpoint: str, user_index: int):
    """단일 주문 요청. 실패해도 예외를 던지지 않고 결과 dict로 반환."""
    try:
        with httpx.Client(timeout=60) as client:
            resp = client.post(
                f"{BASE_URL}/order/{endpoint}/{PRODUCT_ID}",
                json={"user_id": f"sim-user-{user_index}", "quantity": 1},
            )
            data = resp.json()
            return {
                "ok": True,
                "status": data.get("status"),
                "retry_count": data.get("retry_count", 0),
                "duration_ms": data.get("duration_ms"),
            }
    except Exception as e:
        return {"ok": False, "error": str(e)}


def run_experiment(endpoint: str):
    print(f"\n=== [{endpoint}] 실험 시작: 재고 {INITIAL_STOCK}개 / 동시 요청 {CONCURRENT_USERS}건 ===")
    reset_stock()

    start = time.perf_counter()
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = [
            executor.submit(single_order, endpoint, i) for i in range(CONCURRENT_USERS)
        ]
        results = [f.result() for f in concurrent.futures.as_completed(futures)]
    total_elapsed = time.perf_counter() - start

    final_stock = get_stock()

    ok_results = [r for r in results if r["ok"]]
    failed_requests = [r for r in results if not r["ok"]]

    success = [r for r in ok_results if r["status"] == "success"]
    out_of_stock = [r for r in ok_results if r["status"] == "out_of_stock"]
    retry_exhausted = [r for r in ok_results if r["status"] == "retry_exhausted"]

    durations = [r["duration_ms"] for r in ok_results if r.get("duration_ms") is not None]
    durations_sorted = sorted(durations)

    def percentile(data, p):
        if not data:
            return None
        k = int(round((p / 100) * (len(data) - 1)))
        return data[k]

    expected_stock = INITIAL_STOCK - len(success)
    consistency_ok = final_stock == expected_stock and final_stock >= 0

    summary = {
        "endpoint": endpoint,
        "initial_stock": INITIAL_STOCK,
        "concurrent_users": CONCURRENT_USERS,
        "total_elapsed_sec": round(total_elapsed, 4),
        "tps": round(CONCURRENT_USERS / total_elapsed, 2),
        "success_count": len(success),
        "out_of_stock_count": len(out_of_stock),
        "retry_exhausted_count": len(retry_exhausted),
        "network_failed_count": len(failed_requests),
        "final_stock": final_stock,
        "expected_stock": expected_stock,
        "consistency_ok": consistency_ok,
        "total_retries": sum(r.get("retry_count", 0) for r in ok_results),
        "avg_retry_per_request": round(
            sum(r.get("retry_count", 0) for r in ok_results) / len(ok_results), 3
        ) if ok_results else 0,
        "response_time_ms": {
            "p50": percentile(durations_sorted, 50),
            "p95": percentile(durations_sorted, 95),
            "p99": percentile(durations_sorted, 99),
            "min": min(durations_sorted) if durations_sorted else None,
            "max": max(durations_sorted) if durations_sorted else None,
            "mean": round(statistics.mean(durations_sorted), 3) if durations_sorted else None,
        },
    }

    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return summary


def main():
    ensure_product()

    all_results = {}
    for endpoint in ["no-lock", "pessimistic", "optimistic"]:
        all_results[endpoint] = run_experiment(endpoint)

    out_path = RESULTS_DIR / "raw_results.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(all_results, f, indent=2, ensure_ascii=False)

    print(f"\n\n전체 결과가 {out_path} 에 저장되었습니다.")
    print("\n=== 요약 비교 ===")
    print(f"{'방식':12s} {'성공':>6s} {'최종재고':>8s} {'기대재고':>8s} {'정합성':>8s} {'TPS':>8s} {'재시도':>8s}")
    for endpoint, r in all_results.items():
        print(
            f"{endpoint:12s} {r['success_count']:6d} {r['final_stock']:8d} "
            f"{r['expected_stock']:8d} {'OK' if r['consistency_ok'] else 'FAIL':>8s} "
            f"{r['tps']:8.1f} {r['total_retries']:8d}"
        )


if __name__ == "__main__":
    main()
