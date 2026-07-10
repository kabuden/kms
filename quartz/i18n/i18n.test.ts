import test, { describe } from "node:test"
import assert from "node:assert"
import { TRANSLATIONS, i18n, defaultTranslation } from "./index"
import type { ValidLocale } from "./index"

describe("i18n", () => {
  test("defaultTranslation is a valid locale key", () => {
    assert.ok(defaultTranslation in TRANSLATIONS, `"${defaultTranslation}" not found in TRANSLATIONS`)
  })

  test("i18n() returns the translation for a given locale", () => {
    const t = i18n("en-US")
    assert.strictEqual(typeof t.propertyDefaults.title, "string")
    assert.strictEqual(typeof t.propertyDefaults.description, "string")
  })

  const locales = Object.keys(TRANSLATIONS) as ValidLocale[]

  describe("all locales have required top-level keys", () => {
    for (const locale of locales) {
      test(locale, () => {
        const t = TRANSLATIONS[locale]
        assert.ok(t.propertyDefaults, `${locale}: missing propertyDefaults`)
        assert.strictEqual(typeof t.propertyDefaults.title, "string", `${locale}: propertyDefaults.title must be a string`)
        assert.strictEqual(typeof t.propertyDefaults.description, "string", `${locale}: propertyDefaults.description must be a string`)
        assert.ok(t.components, `${locale}: missing components`)
        assert.ok(t.pages, `${locale}: missing pages`)
      })
    }
  })

  describe("all locales have required callout translations", () => {
    const requiredCallouts = [
      "note", "abstract", "info", "todo", "tip",
      "success", "question", "warning", "failure", "danger",
      "bug", "example", "quote",
    ] as const

    for (const locale of locales) {
      test(locale, () => {
        const callout = TRANSLATIONS[locale].components.callout
        for (const key of requiredCallouts) {
          assert.strictEqual(
            typeof callout[key],
            "string",
            `${locale}: callout.${key} must be a string`,
          )
        }
      })
    }
  })

  describe("all locales have required page translations", () => {
    for (const locale of locales) {
      test(locale, () => {
        const { pages } = TRANSLATIONS[locale]

        assert.ok(pages.error, `${locale}: missing pages.error`)
        assert.strictEqual(typeof pages.error.title, "string", `${locale}: pages.error.title`)
        assert.strictEqual(typeof pages.error.notFound, "string", `${locale}: pages.error.notFound`)
        assert.strictEqual(typeof pages.error.home, "string", `${locale}: pages.error.home`)

        assert.ok(pages.folderContent, `${locale}: missing pages.folderContent`)
        assert.strictEqual(typeof pages.folderContent.folder, "string", `${locale}: pages.folderContent.folder`)
        assert.strictEqual(typeof pages.folderContent.itemsUnderFolder, "function", `${locale}: pages.folderContent.itemsUnderFolder must be a function`)

        assert.ok(pages.tagContent, `${locale}: missing pages.tagContent`)
        assert.strictEqual(typeof pages.tagContent.tag, "string", `${locale}: pages.tagContent.tag`)
        assert.strictEqual(typeof pages.tagContent.tagIndex, "string", `${locale}: pages.tagContent.tagIndex`)
        assert.strictEqual(typeof pages.tagContent.itemsUnderTag, "function", `${locale}: pages.tagContent.itemsUnderTag must be a function`)
        assert.strictEqual(typeof pages.tagContent.showingFirst, "function", `${locale}: pages.tagContent.showingFirst must be a function`)
        assert.strictEqual(typeof pages.tagContent.totalTags, "function", `${locale}: pages.tagContent.totalTags must be a function`)
      })
    }
  })

  describe("callable translation functions return strings", () => {
    for (const locale of locales) {
      test(locale, () => {
        const t = TRANSLATIONS[locale]

        const recentNotes = t.components.recentNotes.seeRemainingMore({ remaining: 5 })
        assert.strictEqual(typeof recentNotes, "string", `${locale}: seeRemainingMore must return a string`)

        const readingTime = t.components.contentMeta.readingTime({ minutes: 3 })
        assert.strictEqual(typeof readingTime, "string", `${locale}: readingTime must return a string`)

        const folderItems = t.pages.folderContent.itemsUnderFolder({ count: 2 })
        assert.strictEqual(typeof folderItems, "string", `${locale}: itemsUnderFolder must return a string`)

        const folderSingular = t.pages.folderContent.itemsUnderFolder({ count: 1 })
        assert.strictEqual(typeof folderSingular, "string", `${locale}: itemsUnderFolder(1) must return a string`)

        const tagItems = t.pages.tagContent.itemsUnderTag({ count: 2 })
        assert.strictEqual(typeof tagItems, "string", `${locale}: itemsUnderTag must return a string`)

        const totalTags = t.pages.tagContent.totalTags({ count: 10 })
        assert.strictEqual(typeof totalTags, "string", `${locale}: totalTags must return a string`)
      })
    }
  })
})
