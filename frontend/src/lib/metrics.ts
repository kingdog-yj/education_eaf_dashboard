// 지표 스펙(/api/meta/specs) 기반 포맷·판정 유틸.
// 밴드 수치는 절대 하드코딩하지 않는다 — 전부 MetricSpec에서 온다.
import type { MetricSpec } from "../api/types";

export type SpecMap = Map<string, MetricSpec>;

export function toSpecMap(specs: MetricSpec[]): SpecMap {
  return new Map(specs.map((s) => [s.id, s]));
}

/** 밴드가 있고 값이 [lo, hi] 밖이면 이탈(경계 포함 = 정상). 결측은 판정 제외. */
export function isOutOfSpec(
  value: number | null | undefined,
  spec?: MetricSpec | null,
): boolean {
  if (value == null || !Number.isFinite(value) || !spec) return false;
  if (spec.lo != null && value < spec.lo) return true;
  if (spec.hi != null && value > spec.hi) return true;
  return false;
}

export function hasBand(spec?: MetricSpec | null): boolean {
  return !!spec && (spec.lo != null || spec.hi != null);
}

/** 소수 자릿수·천단위 구분 적용. 결측은 "–". */
export function formatValue(
  value: number | null | undefined,
  decimals = 1,
): string {
  if (value == null || !Number.isFinite(value)) return "–";
  return value.toLocaleString("ko-KR", {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
}

/** 밴드 텍스트(예: "380.0 ~ 410.0 kWh/t"). 밴드 없으면 null. */
export function bandText(spec?: MetricSpec | null): string | null {
  if (!hasBand(spec) || !spec) return null;
  const lo = spec.lo != null ? formatValue(spec.lo, spec.decimals) : "…";
  const hi = spec.hi != null ? formatValue(spec.hi, spec.decimals) : "…";
  return `기준 ${lo} ~ ${hi}`;
}

/** 값이 밴드 내 어디에 위치하는지(0~1). 밴드 밖이면 0/1로 클램프. */
export function bandPosition(
  value: number | null | undefined,
  spec?: MetricSpec | null,
): number | null {
  if (value == null || !Number.isFinite(value)) return null;
  if (!spec || spec.lo == null || spec.hi == null || spec.hi <= spec.lo)
    return null;
  return Math.min(Math.max((value - spec.lo) / (spec.hi - spec.lo), 0), 1);
}

const DATE_FMT = new Intl.DateTimeFormat("ko-KR", {
  year: "numeric",
  month: "long",
  day: "numeric",
});

/** ISO 문자열 → "2026년 8월 20일". 파싱 실패 시 원문 반환. */
export function formatDate(iso: string | null | undefined): string {
  if (!iso) return "–";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : DATE_FMT.format(d);
}
