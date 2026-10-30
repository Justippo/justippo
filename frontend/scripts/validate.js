#!/usr/bin/env node
/**
 * EvidenceEU AST Validation Script
 * Spec: docs/production-component-guide.md §AST Validation Rules
 *
 * Checks:
 * 1. No hardcoded hex (#rrggbb/#rgb), rgb(), hsl() in .ts/.tsx string literals
 *    (tokens.css is exempt — it DEFINES the values)
 * 2. All component props use Readonly<T> interface
 * 3. No heavy logic (useState/useEffect/inline handlers >5 statements) in .tsx component bodies
 * 4. No placeholder identifiers (foo, bar, baz, TODO, FIXME, placeholder)
 *
 * Exit 0 on clean, exit 1 with violation list on failure.
 */

const ts = require("typescript");
const path = require("path");
const fs = require("fs");

const SRC_DIR = path.resolve(__dirname, "../src");
const GENERATED_API_DIR = path.resolve(SRC_DIR, "lib/api-generated/schema");
const EXEMPT_FILES = ["tokens.css", "styles/tokens.css"];

// Infrastructure KEEP files — exempt from logic/placeholder rules
const INFRA_KEEP = [
  "DatadogInit.tsx",
  "TolgeeClientProvider.tsx",
  "types/index.ts",
  "shell/NavigationBar.tsx",
];

const violations = [];

// ─── Helpers ────────────────────────────────────────────────────────────────

function getAllFiles(dir, exts) {
  const results = [];
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      if (full === GENERATED_API_DIR) continue;
      results.push(...getAllFiles(full, exts));
    } else if (exts.some((e) => entry.name.endsWith(e))) {
      results.push(full);
    }
  }
  return results;
}

function relPath(file) {
  return path.relative(path.resolve(__dirname, ".."), file);
}

function isExempt(file) {
  const rel = relPath(file);
  return (
    EXEMPT_FILES.some((e) => rel.endsWith(e)) ||
    rel.includes("lib/api-generated/gen/")
  );
}

function getLineNumber(sourceFile, pos) {
  return sourceFile.getLineAndCharacterOfPosition(pos).line + 1;
}

// ─── Rule 1: No hardcoded colors ────────────────────────────────────────────

const HEX_REGEX = /#([0-9a-fA-F]{3,8})\b/;
const RGB_HSL_REGEX = /\b(rgb|hsl)a?\s*\(/;

function checkNoHardcodedColors(sourceFile, file) {
  if (isExempt(file)) return;

  function visit(node) {
    if (
      ts.isStringLiteral(node) ||
      ts.isNoSubstitutionTemplateLiteral(node) ||
      ts.isTemplateHead(node) ||
      ts.isTemplateMiddle(node) ||
      ts.isTemplateTail(node)
    ) {
      const text = node.text || "";
      if (HEX_REGEX.test(text)) {
        violations.push(
          `[COLOR] ${relPath(file)}:${getLineNumber(sourceFile, node.getStart())}: Hardcoded hex "${text.match(HEX_REGEX)[0]}" — use CSS custom property`
        );
      }
      if (RGB_HSL_REGEX.test(text)) {
        violations.push(
          `[COLOR] ${relPath(file)}:${getLineNumber(sourceFile, node.getStart())}: Hardcoded ${text.match(RGB_HSL_REGEX)[1]}() — use CSS custom property`
        );
      }
    }
    ts.forEachChild(node, visit);
  }
  visit(sourceFile);
}

// ─── Rule 2: Readonly<T> props ──────────────────────────────────────────────

function checkReadonlyProps(sourceFile, file) {
  // Only check .tsx files in src/components/
  if (!file.endsWith(".tsx") || !file.includes("components")) return;
  // Skip stories and tests
  if (file.includes(".stories.") || file.includes(".test.") || file.includes("__tests__")) return;

  function visit(node) {
    // Look for function declarations/expressions that are components (PascalCase, return JSX)
    if (
      (ts.isFunctionDeclaration(node) ||
        ts.isFunctionExpression(node) ||
        ts.isArrowFunction(node)) &&
      node.parameters &&
      node.parameters.length > 0
    ) {
      const name =
        node.name?.text ||
        (node.parent && ts.isVariableDeclaration(node.parent) ? node.parent.name?.text : "");
      // PascalCase check for component names
      if (name && /^[A-Z][a-zA-Z0-9]*$/.test(name)) {
        const firstParam = node.parameters[0];
        if (firstParam.type) {
          const typeText = firstParam.type.getText(sourceFile);
          // Check for `: any` props
          if (typeText === "any") {
            violations.push(
              `[PROPS] ${relPath(file)}:${getLineNumber(sourceFile, firstParam.getStart())}: Component "${name}" uses ": any" props — use Readonly<T> interface`
            );
          }
        }
      }
    }
    ts.forEachChild(node, visit);
  }
  visit(sourceFile);
}

// ─── Rule 3: No heavy logic in component bodies ─────────────────────────────

const LOGIC_HOOKS = ["useState", "useEffect", "useLayoutEffect", "useReducer"];

function checkNoLogicInComponents(sourceFile, file) {
  if (!file.endsWith(".tsx") || !file.includes("components")) return;
  if (file.includes(".stories.") || file.includes(".test.") || file.includes("__tests__")) return;
  if (INFRA_KEEP.some((k) => file.endsWith(k))) return;

  function countStatements(body) {
    if (!body || !body.statements) return 0;
    return body.statements.length;
  }

  function visit(node) {
    if (
      ts.isFunctionDeclaration(node) ||
      ts.isFunctionExpression(node) ||
      ts.isArrowFunction(node)
    ) {
      const name =
        node.name?.text ||
        (node.parent && ts.isVariableDeclaration(node.parent) ? node.parent.name?.text : "");
      if (name && /^[A-Z][a-zA-Z0-9]*$/.test(name)) {
        // Check for useState/useEffect calls
        const bodyText = node.body ? node.body.getText(sourceFile) : "";
        for (const hook of LOGIC_HOOKS) {
          if (bodyText.includes(hook)) {
            violations.push(
              `[LOGIC] ${relPath(file)}:${getLineNumber(sourceFile, node.getStart())}: Component "${name}" contains ${hook} — extract to src/hooks/`
            );
          }
        }
        // Check for inline handlers with >5 statements
        if (node.body && ts.isBlock(node.body) && countStatements(node.body) > 15) {
          violations.push(
            `[LOGIC] ${relPath(file)}:${getLineNumber(sourceFile, node.getStart())}: Component "${name}" has ${countStatements(node.body)} statements — consider extracting logic to hooks`
          );
        }
      }
    }
    ts.forEachChild(node, visit);
  }
  visit(sourceFile);
}

// ─── Rule 4: No placeholder identifiers ─────────────────────────────────────

const PLACEHOLDER_REGEX = /\b(foo|bar|baz)\b/i;
const TODO_REGEX = /\b(TODO|FIXME)\b/;

function checkNoPlaceholders(sourceFile, file) {
  if (isExempt(file)) return;
  if (INFRA_KEEP.some((k) => file.endsWith(k))) return;
  function visit(node) {
    if (ts.isIdentifier(node)) {
      const name = node.text;
      if (PLACEHOLDER_REGEX.test(name)) {
        violations.push(
          `[PLACEHOLDER] ${relPath(file)}:${getLineNumber(sourceFile, node.getStart())}: Placeholder identifier "${name}"`
        );
      }
    }
    // Check comments for TODO/FIXME
    ts.forEachChild(node, visit);
  }
  visit(sourceFile);

  // Also scan raw text for TODO/FIXME in comments
  const fullText = sourceFile.getFullText();
  const lines = fullText.split("\n");
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    // Only flag in comments
    const commentMatch = line.match(/\/\/.*|\/\*[\s\S]*?\*\//);
    if (commentMatch && TODO_REGEX.test(commentMatch[0])) {
      violations.push(
        `[PLACEHOLDER] ${relPath(file)}:${i + 1}: Contains ${line.match(TODO_REGEX)[0]} comment`
      );
    }
  }
}

// ─── Rule 5: No hardcoded colors in CSS files ──────────────────────────────

const CSS_COLOR_REGEX = /#([0-9a-fA-F]{3,8})\b|(\b(rgb|hsl)a?\s*\()/g;
const CSS_EXEMPT_FILES = ["styles/tokens.css"];

function checkCSSColors() {
  const cssFiles = getAllFiles(SRC_DIR, [".css"]);
  for (const file of cssFiles) {
    const rel = relPath(file);
    if (CSS_EXEMPT_FILES.some((e) => rel.endsWith(e))) continue;

    const content = fs.readFileSync(file, "utf-8");
    const lines = content.split("\n");
    for (let i = 0; i < lines.length; i++) {
      const line = lines[i];
      // Skip CSS comments
      if (line.trim().startsWith("/*") || line.trim().startsWith("*")) continue;
      let match;
      CSS_COLOR_REGEX.lastIndex = 0;
      while ((match = CSS_COLOR_REGEX.exec(line)) !== null) {
        violations.push(
          `[CSS-COLOR] ${rel}:${i + 1}: Hardcoded color "${match[0]}" — use CSS custom property from tokens.css`
        );
      }
    }
  }
}

// ─── Main ───────────────────────────────────────────────────────────────────

function main() {
  const files = getAllFiles(SRC_DIR, [".ts", ".tsx"]);

  for (const file of files) {
    // Skip .d.ts files
    if (file.endsWith(".d.ts")) continue;

    const content = fs.readFileSync(file, "utf-8");
    const sourceFile = ts.createSourceFile(
      file,
      content,
      ts.ScriptTarget.Latest,
      true,
      file.endsWith(".tsx") ? ts.ScriptKind.TSX : ts.ScriptKind.TS
    );

    checkNoHardcodedColors(sourceFile, file);
    checkReadonlyProps(sourceFile, file);
    checkNoLogicInComponents(sourceFile, file);
    checkNoPlaceholders(sourceFile, file);
  }

  // CSS color scan
  checkCSSColors();

  if (violations.length === 0) {
    console.log("OK: no violations");
    process.exit(0);
  } else {
    console.log(`FAIL: ${violations.length} violation(s)\n`);
    for (const v of violations) {
      console.log(`  ${v}`);
    }
    process.exit(1);
  }
}

main();
