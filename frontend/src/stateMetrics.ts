export function finiteCount(value: unknown): number {
  if (value === null || value === undefined || value === '' || typeof value === 'boolean') return 0;
  const count = Number(value);
  return Number.isFinite(count) && count >= 0 ? Math.floor(count) : 0;
}
