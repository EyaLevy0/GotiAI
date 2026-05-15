import * as vscode from "vscode";

export class Logger {
  private readonly channel: vscode.OutputChannel;

  constructor(name = "Godot Context Agent") {
    this.channel = vscode.window.createOutputChannel(name);
  }

  info(msg: string, ...rest: unknown[]): void {
    this.channel.appendLine(`[info]  ${msg}${rest.length ? " " + JSON.stringify(rest) : ""}`);
  }

  warn(msg: string, ...rest: unknown[]): void {
    this.channel.appendLine(`[warn]  ${msg}${rest.length ? " " + JSON.stringify(rest) : ""}`);
  }

  error(msg: string, err?: unknown): void {
    const detail = err instanceof Error ? `${err.message}\n${err.stack ?? ""}` : String(err ?? "");
    this.channel.appendLine(`[error] ${msg}${detail ? "\n" + detail : ""}`);
  }

  dispose(): void {
    this.channel.dispose();
  }
}
