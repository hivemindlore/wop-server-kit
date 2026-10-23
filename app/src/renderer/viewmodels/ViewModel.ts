import { useEffect, useSyncExternalStore } from 'react'
import type { ModelName, ModelStates, Unsubscribe, WopApi } from '@shared/api'

/**
 * Base for the ViewModels: holds what one screen shows (V), tells React when it changes, and keeps a copy
 * of the model states it is built from. Views read `useViewModel(vm)` and call the vm's methods; they never
 * talk to window.wop themselves.
 *
 * A vm listens to the models from the start; dispose() stops that and activate() starts it again. React
 * mounts every view twice in development (StrictMode), so a vm must come back to life after a dispose.
 */
export abstract class ViewModel<V> {
  private listeners = new Set<() => void>()
  private sources: (() => Unsubscribe)[] = []
  private subscriptions: Unsubscribe[] = []
  private active = true
  private view: V | undefined

  // Subclass fields aren't set yet while this runs, so the first view is built on first use
  constructor(protected readonly api: WopApi) {}

  /** Builds what the view shows from the mirrored model states and the vm's own fields. */
  protected abstract present(): V

  getSnapshot = (): V => (this.view ??= this.present())

  subscribe = (listener: () => void): (() => void) => {
    this.listeners.add(listener)
    return () => this.listeners.delete(listener)
  }

  /** Call after changing anything present() reads. */
  protected changed(): void {
    this.view = this.present()
    for (const listener of this.listeners) listener()
  }

  /** Keep a live copy of a model's state: the current one now, every new one as it comes. */
  protected mirror<M extends ModelName>(model: M, apply: (state: ModelStates[M]) => void): void {
    this.source(() => {
      let live = true
      const unsubscribe = this.api.onState(model, (state) => {
        apply(state)
        this.changed()
      })
      void this.api.get(model).then((state) => {
        if (!live) return
        apply(state)
        this.changed()
      })
      return () => {
        live = false
        unsubscribe()
      }
    })
  }

  /** Something to listen to while the vm is active: start() begins listening and returns how to stop. */
  protected source(start: () => Unsubscribe): void {
    this.sources.push(start)
    if (this.active) this.subscriptions.push(start())
  }

  activate(): void {
    if (this.active) return
    this.active = true
    this.subscriptions = this.sources.map((start) => start())
  }

  dispose(): void {
    this.active = false
    for (const unsubscribe of this.subscriptions) unsubscribe()
    this.subscriptions = []
  }
}

export function useViewModel<V>(vm: ViewModel<V>): V {
  return useSyncExternalStore(vm.subscribe, vm.getSnapshot)
}

/** Keeps a vm listening while its view is mounted. */
export function useActive<T extends { activate(): void; dispose(): void }>(vm: T): T {
  useEffect(() => {
    vm.activate()
    return () => vm.dispose()
  }, [vm])
  return vm
}
