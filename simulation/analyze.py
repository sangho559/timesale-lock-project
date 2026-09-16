"""
3단계: 시뮬레이션 결과(raw_results.json)를 읽어 그래프/표 이미지를 생성.

생성물 (results/ 폴더):
- 01_processing_time_comparison.png : 3방식 전체 처리시간 & TPS 비교
- 02_response_time_percentiles.png  : p50/p95/p99 응답시간 비교
- 03_consistency_table.png          : 정합성(재고 붕괴 여부) 비교 표
- 04_success_vs_failure.png         : 성공/실패(재고부족) 건수 비교
"""
import json
from pathlib import Path

import matplotlib
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm

matplotlib.use("Agg")

# ---- 한글 폰트 설정 (나눔고딕) ----
NANUM_PATH = "/usr/share/fonts/truetype/nanum/NanumGothic.ttf"
if Path(NANUM_PATH).exists():
    fm.fontManager.addfont(NANUM_PATH)
    plt.rcParams["font.family"] = fm.FontProperties(fname=NANUM_PATH).get_name()
plt.rcParams["axes.unicode_minus"] = False

RESULTS_DIR = Path(__file__).resolve().parent.parent / "results"
INPUT_PATH = RESULTS_DIR / "raw_results.json"

LABELS = {
    "no-lock": "락 없음\n(Race Condition)",
    "pessimistic": "비관적 락\n(SELECT FOR UPDATE)",
    "optimistic": "낙관적 락\n(Version 기반 CAS)",
}
COLORS = {
    "no-lock": "#e74c3c",       # 문제 상황 강조 - 빨강 계열
    "pessimistic": "#3498db",   # 파랑 계열
    "optimistic": "#2ecc71",    # 초록 계열
}
ORDER = ["no-lock", "pessimistic", "optimistic"]


def load_data():
    with open(INPUT_PATH, encoding="utf-8") as f:
        return json.load(f)


def chart_processing_time_and_tps(data):
    fig, axes = plt.subplots(1, 2, figsize=(12, 5))

    # (1) 전체 처리 시간
    times = [data[k]["total_elapsed_sec"] for k in ORDER]
    labels = [LABELS[k] for k in ORDER]
    colors = [COLORS[k] for k in ORDER]

    bars = axes[0].bar(labels, times, color=colors)
    axes[0].set_title(f"동시 요청 {data[ORDER[0]]['concurrent_users']}건 처리 총 소요 시간", fontsize=13, fontweight="bold")
    axes[0].set_ylabel("소요 시간 (초)")
    for bar, v in zip(bars, times):
        axes[0].text(bar.get_x() + bar.get_width() / 2, v, f"{v:.2f}s",
                     ha="center", va="bottom", fontsize=10)

    # (2) TPS
    tps = [data[k]["tps"] for k in ORDER]
    bars2 = axes[1].bar(labels, tps, color=colors)
    axes[1].set_title("초당 처리량 (TPS)", fontsize=13, fontweight="bold")
    axes[1].set_ylabel("TPS (요청/초)")
    for bar, v in zip(bars2, tps):
        axes[1].text(bar.get_x() + bar.get_width() / 2, v, f"{v:.1f}",
                     ha="center", va="bottom", fontsize=10)

    plt.tight_layout()
    out = RESULTS_DIR / "01_processing_time_comparison.png"
    plt.savefig(out, dpi=150)
    plt.close()
    print(f"저장: {out}")


def chart_response_percentiles(data):
    fig, ax = plt.subplots(figsize=(10, 6))

    x = range(len(ORDER))
    width = 0.25
    percentiles = ["p50", "p95", "p99"]
    pct_colors = ["#95a5a6", "#f39c12", "#c0392b"]

    for i, p in enumerate(percentiles):
        values = [data[k]["response_time_ms"][p] for k in ORDER]
        positions = [xi + (i - 1) * width for xi in x]
        bars = ax.bar(positions, values, width=width, label=p.upper(), color=pct_colors[i])
        for bar, v in zip(bars, values):
            ax.text(bar.get_x() + bar.get_width() / 2, v, f"{v:.0f}",
                    ha="center", va="bottom", fontsize=8)

    ax.set_xticks(list(x))
    ax.set_xticklabels([LABELS[k] for k in ORDER])
    ax.set_ylabel("응답 시간 (ms)")
    ax.set_title("방식별 응답 시간 분포 (p50 / p95 / p99)", fontsize=13, fontweight="bold")
    ax.legend()

    plt.tight_layout()
    out = RESULTS_DIR / "02_response_time_percentiles.png"
    plt.savefig(out, dpi=150)
    plt.close()
    print(f"저장: {out}")


def chart_consistency_table(data):
    fig, ax = plt.subplots(figsize=(12, 3.5))
    ax.axis("off")
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)

    columns = ["방식", "초기 재고", "성공 처리 건수", "최종 재고", "기대 재고", "정합성"]
    rows = []
    cell_colors = []
    for k in ORDER:
        d = data[k]
        ok = d["consistency_ok"]
        rows.append([
            LABELS[k].replace("\n", " "),
            d["initial_stock"],
            d["success_count"],
            d["final_stock"],
            d["expected_stock"],
            "정상" if ok else "붕괴 (오버셀링 발생)",
        ])
        row_color = "#eafaf1" if ok else "#fdecea"
        cell_colors.append([row_color] * len(columns))

    col_widths = [0.30, 0.13, 0.17, 0.13, 0.13, 0.24]

    table = ax.table(
        cellText=rows,
        colLabels=columns,
        cellColours=cell_colors,
        colColours=["#dfe6e9"] * len(columns),
        colWidths=col_widths,
        loc="center",
        cellLoc="center",
        bbox=[0, 0, 1, 0.85],
    )
    table.auto_set_font_size(False)
    table.set_fontsize(11)

    # 첫 번째 열(방식)은 텍스트가 길어서 왼쪽 정렬로 변경
    for (row, col), cell in table.get_celld().items():
        if col == 0:
            cell.set_text_props(ha="left")
            cell.PAD = 0.02

    ax.set_title("동시 요청 시 데이터 정합성 비교", fontsize=13, fontweight="bold", pad=20)

    plt.tight_layout()
    out = RESULTS_DIR / "03_consistency_table.png"
    plt.savefig(out, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"저장: {out}")


def chart_success_vs_failure(data):
    fig, ax = plt.subplots(figsize=(10, 6))

    success = [data[k]["success_count"] for k in ORDER]
    out_of_stock = [data[k]["out_of_stock_count"] for k in ORDER]
    retry_exhausted = [data[k]["retry_exhausted_count"] for k in ORDER]
    totals = [data[k]["concurrent_users"] for k in ORDER]

    labels = [LABELS[k] for k in ORDER]
    x = range(len(ORDER))

    ax.bar(x, success, label="구매 성공", color="#2ecc71")
    ax.bar(x, out_of_stock, bottom=success, label="재고 부족(정상 거절)", color="#95a5a6")
    bottom2 = [s + o for s, o in zip(success, out_of_stock)]
    ax.bar(x, retry_exhausted, bottom=bottom2, label="재시도 초과 실패", color="#c0392b")

    y_max = max(totals)
    ax.set_ylim(0, y_max * 1.18)

    for i, k in enumerate(ORDER):
        total = data[k]["concurrent_users"]
        ax.text(i, total + y_max * 0.03, f"총 요청 {total}건\n(재고 {data[k]['initial_stock']}개)",
                ha="center", fontsize=9)

    ax.set_xticks(list(x))
    ax.set_xticklabels(labels)
    ax.set_ylabel("요청 건수")
    ax.set_title("방식별 요청 처리 결과 분해", fontsize=13, fontweight="bold", pad=45)
    ax.legend(loc="upper left", bbox_to_anchor=(0.02, 0.85))

    plt.tight_layout()
    out = RESULTS_DIR / "04_success_vs_failure.png"
    plt.savefig(out, dpi=150)
    plt.close()
    print(f"저장: {out}")


def main():
    data = load_data()
    chart_processing_time_and_tps(data)
    chart_response_percentiles(data)
    chart_consistency_table(data)
    chart_success_vs_failure(data)
    print("\n모든 그래프 생성 완료.")


if __name__ == "__main__":
    main()
