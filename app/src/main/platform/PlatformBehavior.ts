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
  /** This computer's installer in a GitHub release (the names electron-builder.yml gives them); null: none. */
  updateAssetName(version: string): string | null
  /** Start installing a downloaded update (its sha256 is already checked). */
  installUpdate(file: string): Promise<UpdateInstall>
}

export type UpdateInstall =
  /** The app quits now; relaunch: start it again (else the installer opens it). */
  | { kind: 'quit'; relaunch: boolean }
  /** The user finishes it: show message (and the file, if reveal). */
  | { kind: 'manual'; message: string; reveal: boolean }

/** Starts a program and resolves with its exit code (null if it couldn't start). */
export type Runner = (command: string, args: string[], options: { detached: boolean }) => Promise<number | null>
