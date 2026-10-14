import { execSync } from "node:child_process";
import { writeFileSync, unlinkSync, existsSync } from "node:fs";
import { resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const rootDir = resolve(__dirname, "..");
const tempOpenApiPath = resolve(rootDir, "openapi.temp.json");
const outputTypesPath = resolve(rootDir, "src", "types", "api.generated.ts");

console.log("[generate-types] Extracting OpenAPI specification from backend...");

let openapiJson = null;

// Try fetching from running backend first
try {
  const res = execSync("curl -s http://127.0.0.1:8000/openapi.json", { encoding: "utf-8" });
  if (res && res.includes("openapi")) {
    openapiJson = res;
    console.log("[generate-types] Fetched OpenAPI schema from active server at http://127.0.0.1:8000");
  }
} catch {
  // Server not running, fallback to python import
}

// Fallback: extract directly via backend Python interpreter
if (!openapiJson) {
  try {
    const pythonCmd = `powershell -Command "$env:PYTHONPATH='backend'; backend\\.venv\\Scripts\\python.exe -c \\"import json; from app.main import app; print(json.dumps(app.openapi()))\\""`;
    const res = execSync(pythonCmd, { cwd: resolve(rootDir, ".."), encoding: "utf-8" });
    if (res && res.includes("openapi")) {
      openapiJson = res;
      console.log("[generate-types] Extracted OpenAPI schema directly via FastAPI Python application.");
    }
  } catch (err) {
    console.error("[generate-types] Failed to extract OpenAPI via Python:", err.message);
  }
}

if (!openapiJson) {
  console.error("[generate-types] ERROR: Could not retrieve OpenAPI specification.");
  process.exit(1);
}

writeFileSync(tempOpenApiPath, openapiJson, "utf-8");

console.log("[generate-types] Running openapi-typescript generator...");
try {
  execSync(`npx openapi-typescript "${tempOpenApiPath}" -o "${outputTypesPath}"`, {
    cwd: rootDir,
    stdio: "inherit",
  });
  console.log(`[generate-types] Generated TypeScript types successfully at ${outputTypesPath}`);
} finally {
  if (existsSync(tempOpenApiPath)) {
    unlinkSync(tempOpenApiPath);
  }
}

