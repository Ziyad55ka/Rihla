import fs from 'node:fs'
import path from 'node:path'
import ts from 'typescript'

const dictionaryFile = ts.createSourceFile('translations.ts', fs.readFileSync('src/lib/translations.ts', 'utf8'), ts.ScriptTarget.Latest, true)
const dictionary = new Map()
const problems = []
const placeholders = value => [...value.matchAll(/\{(\w+)\}/g)].map(match => match[1]).sort().join(',')
function dictionaryKeys(node) {
  if (ts.isPropertyAssignment(node) && ts.isStringLiteral(node.name) && ts.isStringLiteral(node.initializer)) {
    const key = node.name.text, value = node.initializer.text
    if (dictionary.has(key)) problems.push(`Duplicate translation: ${key}`)
    if (!value.trim() || placeholders(key) !== placeholders(value)) problems.push(`Invalid translation or placeholders: ${key}`)
    dictionary.set(key, value)
  }
  ts.forEachChild(node, dictionaryKeys)
}
dictionaryKeys(dictionaryFile)
function files(directory) {
  return fs.readdirSync(directory, { withFileTypes: true }).flatMap(entry => entry.isDirectory() ? files(path.join(directory, entry.name)) : [path.join(directory, entry.name)])
}
function check(key, file) { if (!dictionary.has(key)) problems.push(`${file}: missing Arabic translation for ${JSON.stringify(key)}`) }
function technicalAttribute(node) {
  for (let parent = node.parent; parent; parent = parent.parent) {
    if (ts.isJsxAttribute(parent)) return !['placeholder', 'title', 'aria-label'].includes(parent.name.text)
    if (ts.isStatement(parent)) break
  }
  return false
}
for (const file of files('src').filter(file => /\.tsx?$/.test(file) && !/\.test\./.test(file) && !/lib[\\/](translations|language)\./.test(file))) {
  const source = ts.createSourceFile(file, fs.readFileSync(file, 'utf8'), ts.ScriptTarget.Latest, true, file.endsWith('.tsx') ? ts.ScriptKind.TSX : ts.ScriptKind.TS)
  function visit(node) {
    if (ts.isJsxText(node)) {
      const copy = node.getText(source).trim().replace(/\s+/g, ' ')
      if (/[a-zA-Z]{2}/.test(copy) && !['rihla', 'Supabase'].includes(copy)) problems.push(`${file}: untranslated JSX text ${JSON.stringify(copy)}`)
    }
    if (ts.isJsxAttribute(node) && ['placeholder', 'title', 'aria-label'].includes(node.name.text) && node.initializer && ts.isStringLiteral(node.initializer) && !node.initializer.text.includes('@')) problems.push(`${file}: untranslated ${node.name.text}`)
    if (ts.isCallExpression(node) && ts.isIdentifier(node.expression) && node.expression.text === 't' && node.arguments[0] && ts.isStringLiteral(node.arguments[0])) check(node.arguments[0].text, file)
    // Also check messages returned by helpers and data-driven labels/placeholders.
    if (!file.endsWith('PageMotion.tsx') && ts.isStringLiteral(node) && /[A-Za-z]/.test(node.text) && node.text.includes(' ') && !/^[a-z0-9_-]+(?: [a-z0-9_-]+)*$/.test(node.text)
      && !technicalAttribute(node)) check(node.text, file)
    ts.forEachChild(node, visit)
  }
  visit(source)
}
if (problems.length) { console.error([...new Set(problems)].join('\n')); process.exitCode = 1 }
else console.log(`Translation coverage passed (${dictionary.size} Arabic strings; JSX, messages and placeholders checked).`)
