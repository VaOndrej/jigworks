import * as vscode from "vscode";

export function activate(context: vscode.ExtensionContext): void {
  context.subscriptions.push(
    vscode.commands.registerCommand("jigworks.hello", () => {
      vscode.window.showInformationMessage("Hello from Jigworks");
      return "hello";
    }),
  );
}

export function deactivate(): void {}
