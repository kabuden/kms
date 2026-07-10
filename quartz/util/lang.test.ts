import test, { describe } from "node:test"
import assert from "node:assert"
import { capitalize, classNames } from "./lang"

describe("capitalize", () => {
  test("capitalizes the first character", () => {
    assert.strictEqual(capitalize("hello"), "Hello")
  })

  test("leaves already-capitalized string unchanged", () => {
    assert.strictEqual(capitalize("Hello"), "Hello")
  })

  test("handles single character", () => {
    assert.strictEqual(capitalize("a"), "A")
  })

  test("only changes the first character", () => {
    assert.strictEqual(capitalize("hELLO"), "HELLO")
  })

  test("handles empty string", () => {
    assert.strictEqual(capitalize(""), "")
  })
})

describe("classNames", () => {
  test("joins multiple class strings", () => {
    assert.strictEqual(classNames(undefined, "foo", "bar"), "foo bar")
  })

  test("prepends displayClass when provided", () => {
    assert.strictEqual(classNames("mobile-only", "foo", "bar"), "foo bar mobile-only")
  })

  test("prepends desktop-only displayClass", () => {
    assert.strictEqual(classNames("desktop-only", "nav"), "nav desktop-only")
  })

  test("handles no extra classes with a displayClass", () => {
    assert.strictEqual(classNames("mobile-only"), "mobile-only")
  })

  test("handles no arguments", () => {
    assert.strictEqual(classNames(undefined), "")
  })

  test("handles single class without displayClass", () => {
    assert.strictEqual(classNames(undefined, "only-class"), "only-class")
  })
})
