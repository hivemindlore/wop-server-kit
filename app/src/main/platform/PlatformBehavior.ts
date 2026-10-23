// What the app itself does differently per OS (the Strategy pattern, like kit/mcp/wop/platforms in the kit).
// main/index.ts picks one behavior at startup and hands it to the parts that need it; nothing else in the
// app checks which OS it runs on. Everything about the server, the firewall and the setup is in the kit.

export interface PlatformBehavior {
  readonly name: 'windows' | 'mac' | 'linux'
  /** Where the kit is installed (the same folder the .bat / .sh use). */
  defaultKitRoot(): string
  /** File name of uv, the helper that provides Python for the kit. */
  readonly uvFileName: string
  /** Folder under resources/uv with this OS's uv. */
  readonly uvResourceDir: string
  /** Make a copied program runnable. */
  makeExecutable(path: string): Promise<void>
}
