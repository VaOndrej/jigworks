import * as fs from "node:fs";
import * as path from "node:path";
import Mocha from "mocha";

export function run(): Promise<void> {
  const grep = process.env.JIGWORKS_TEST_GREP;
  const mocha = new Mocha({ ui: "tdd", color: true, timeout: 180000, ...(grep ? { grep } : {}) });
  for (const f of fs.readdirSync(__dirname).filter((f) => f.endsWith(".test.js")).sort()) {
    mocha.addFile(path.resolve(__dirname, f));
  }
  return new Promise((resolve, reject) => {
    mocha.run((failures) => (failures > 0 ? reject(new Error(`${failures} tests failed`)) : resolve()));
  });
}
