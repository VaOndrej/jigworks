import * as assert from "node:assert/strict";
import * as vscode from "vscode";

suite("Jigworks extension skeleton", () => {
  test("hello command is registered and runs", async () => {
    const ext = vscode.extensions.getExtension("jigworks.vscode");
    assert.ok(ext, "extension is installed in the test host");
    await ext.activate();
    const result = await vscode.commands.executeCommand("jigworks.hello");
    assert.equal(result, "hello");
  });
});
