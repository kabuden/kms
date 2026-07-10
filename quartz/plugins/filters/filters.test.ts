import test, { describe } from "node:test"
import assert from "node:assert"
import { RemoveDrafts } from "./draft"
import { ExplicitPublish } from "./explicit"

// Minimal mock vfile with only the frontmatter fields each filter reads
function makeVFile(frontmatter: Record<string, unknown>) {
  return { data: { frontmatter } } as any
}

const ctx = {} as any
const tree = {} as any

describe("RemoveDrafts", () => {
  const filter = RemoveDrafts()

  test("publishes a file with no draft flag", () => {
    const vfile = makeVFile({})
    assert.strictEqual(filter.shouldPublish(ctx, [tree, vfile]), true)
  })

  test("publishes a file with draft: false", () => {
    const vfile = makeVFile({ draft: false })
    assert.strictEqual(filter.shouldPublish(ctx, [tree, vfile]), true)
  })

  test("suppresses a file with draft: true", () => {
    const vfile = makeVFile({ draft: true })
    assert.strictEqual(filter.shouldPublish(ctx, [tree, vfile]), false)
  })

  test("publishes when frontmatter is missing entirely", () => {
    const vfile = { data: {} } as any
    assert.strictEqual(filter.shouldPublish(ctx, [tree, vfile]), true)
  })
})

describe("ExplicitPublish", () => {
  const filter = ExplicitPublish()

  test("suppresses a file with no publish flag", () => {
    const vfile = makeVFile({})
    assert.strictEqual(filter.shouldPublish(ctx, [tree, vfile]), false)
  })

  test("publishes a file with publish: true", () => {
    const vfile = makeVFile({ publish: true })
    assert.strictEqual(filter.shouldPublish(ctx, [tree, vfile]), true)
  })

  test("suppresses a file with publish: false", () => {
    const vfile = makeVFile({ publish: false })
    assert.strictEqual(filter.shouldPublish(ctx, [tree, vfile]), false)
  })

  test("suppresses when frontmatter is missing entirely", () => {
    const vfile = { data: {} } as any
    assert.strictEqual(filter.shouldPublish(ctx, [tree, vfile]), false)
  })
})
