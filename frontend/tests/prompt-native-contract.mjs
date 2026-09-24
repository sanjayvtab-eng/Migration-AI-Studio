import { readFileSync } from "node:fs";

const app = readFileSync(new URL("../src/App.tsx", import.meta.url), "utf8");
const required = [
  "2.4.1 BRONZE_TARGET_CONSISTENCY",
  "Parse and Ground Prompt",
  "Approve Exact Plan",
  "Validate in Databricks",
  "/prompt-specifications",
  "/deploy-dev",
  "/trace",
];
for (const value of required) {
  if (!app.includes(value)) throw new Error(`Missing prompt-native UI contract: ${value}`);
}
console.log(`prompt-native frontend contract passed (${required.length} checks)`);
