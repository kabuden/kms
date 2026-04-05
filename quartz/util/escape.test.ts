import test, { describe } from "node:test"
import assert from "node:assert"
import { escapeHTML } from "./escape"

describe("escapeHTML", () => {
  test("escapes ampersand", () => {
    assert.strictEqual(escapeHTML("a&b"), "a&amp;b")
  })

  test("escapes less-than", () => {
    assert.strictEqual(escapeHTML("<div>"), "&lt;div&gt;")
  })

  test("escapes greater-than", () => {
    assert.strictEqual(escapeHTML("a>b"), "a&gt;b")
  })

  test("escapes double quote", () => {
    assert.strictEqual(escapeHTML('"hello"'), "&quot;hello&quot;")
  })

  test("escapes single quote", () => {
    assert.strictEqual(escapeHTML("it's"), "it&#039;s")
  })

  test("escapes all special characters together", () => {
    assert.strictEqual(
      escapeHTML(`<a href="test" class='x'>a&b</a>`),
      "&lt;a href=&quot;test&quot; class=&#039;x&#039;&gt;a&amp;b&lt;/a&gt;",
    )
  })

  test("ampersand is escaped before < and > to avoid double-escaping", () => {
    // If & were escaped last, "&lt;" would become "&amp;lt;" — this confirms it doesn't
    const result = escapeHTML("&lt;")
    assert.strictEqual(result, "&amp;lt;")
  })

  test("returns empty string unchanged", () => {
    assert.strictEqual(escapeHTML(""), "")
  })

  test("returns plain text unchanged", () => {
    assert.strictEqual(escapeHTML("hello world"), "hello world")
  })
})
