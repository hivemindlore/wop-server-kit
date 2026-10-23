/** A model's state plus change notification. States are replaced, never changed in place. */
export class StateModel<S extends object> {
  private listeners = new Set<(state: S) => void>()

  constructor(private state: S) {}

  getState(): S {
    return this.state
  }

  subscribe(listener: (state: S) => void): () => void {
    this.listeners.add(listener)
    return () => this.listeners.delete(listener)
  }

  protected update(patch: Partial<S>): void {
    this.state = { ...this.state, ...patch }
    for (const listener of this.listeners) listener(this.state)
  }
}

export function messageOf(error: unknown): string {
  return error instanceof Error ? error.message : String(error)
}
