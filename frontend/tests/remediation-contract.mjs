import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { finiteCount } from '../src/stateMetrics.ts';

for (const value of [undefined, null, NaN, Infinity, -3, 'invalid', true, '']) assert.equal(finiteCount(value), 0);
assert.equal(finiteCount('31'),31);
assert.equal(finiteCount(42.9),42);
const source=readFileSync(new URL('../src/App.tsx',import.meta.url),'utf8');
assert.equal((source.match(/onClick=\{openPromotionAuthorization\}/g)||[]).length,2);
assert(source.includes('autoAuthLoading || !autoPromotionStatus?.preflight?.eligible'));
assert(!source.includes('verifiedToSkip || 42'));
assert(source.includes('document.visibilityState === "visible"'));
console.log('Remediation frontend contracts passed; browser acceptance remains separate.');
