const BASE_URL = "http://localhost:8000";

export const LOCK_MODES = [
  {
    key: "no-lock",
    label: "락 없음",
    sub: "Race Condition",
    endpoint: "no-lock",
    tone: "danger",
    desc: "읽고-판단-쓰는 사이 보호장치가 없어 동시 요청 시 재고가 깨질 수 있습니다.",
  },
  {
    key: "pessimistic",
    label: "비관적 락",
    sub: "SELECT ... FOR UPDATE",
    endpoint: "pessimistic",
    tone: "info",
    desc: "먼저 온 요청이 행을 잠그고, 다른 요청은 처리가 끝날 때까지 대기합니다.",
  },
  {
    key: "optimistic",
    label: "낙관적 락",
    sub: "Version 기반 CAS",
    endpoint: "optimistic",
    tone: "success",
    desc: "락 없이 진행하되 버전이 바뀌었으면 실패로 보고 자동 재시도합니다.",
  },
];

export async function fetchProduct(productId) {
  const res = await fetch(`${BASE_URL}/product/${productId}`);
  if (!res.ok) throw new Error("상품 조회 실패");
  return res.json();
}

export async function createProduct({ name, stock, price }) {
  const res = await fetch(`${BASE_URL}/product/`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, stock, price }),
  });
  if (!res.ok) throw new Error("상품 생성 실패");
  return res.json();
}

export async function resetStock(productId, stock) {
  const res = await fetch(
    `${BASE_URL}/product/${productId}/reset-stock?stock=${stock}`,
    { method: "POST" }
  );
  if (!res.ok) throw new Error("재고 초기화 실패");
  return res.json();
}

export async function placeOrder(endpoint, productId, userId) {
  const res = await fetch(`${BASE_URL}/order/${endpoint}/${productId}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ user_id: userId, quantity: 1 }),
  });
  const data = await res.json();
  return data;
}
