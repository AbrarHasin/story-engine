// Unit tests for src/lib/bullets.ts. Run: npm run test:unit (Node's built-in runner, no extra deps).
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { normalizeBullets, bulletsFromText } from '../src/lib/bullets.ts'

test('plain bullets pass through, blanks dropped', () => {
  assert.deepEqual(normalizeBullets(['One', '  ', 'Two ']), ['One', 'Two'])
})

test('a complete JSON array bullet expands into items', () => {
  assert.deepEqual(normalizeBullets(['["Fact one", "Fact \\"two\\""]']), ['Fact one', 'Fact "two"'])
})

test('a truncated JSON array keeps only its complete items', () => {
  const raw = '["Honeybee swarms send out scouts.", "A waggle dance encodes direction.", "A swarm can reach a collec'
  assert.deepEqual(normalizeBullets([raw]), [
    'Honeybee swarms send out scouts.',
    'A waggle dance encodes direction.',
  ])
})

test('text that merely starts with [ but has no strings is kept as is', () => {
  assert.deepEqual(normalizeBullets(['[citation needed] a claim']), ['[citation needed] a claim'])
})

test('DB text with a raw JSON line becomes bullets', () => {
  assert.deepEqual(bulletsFromText('["a", "b"]'), ['a', 'b'])
  assert.deepEqual(bulletsFromText('first\nsecond\n'), ['first', 'second'])
})
