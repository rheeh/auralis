// A request is valid only in its captured workspace and until a newer request.
export function createRequestScope(context) {
  let revision = 0
  let disposed = false
  let epoch = 0
  return {
    capture() { return { key: context(), epoch } },
    sameContext(token) { return !disposed && token.key === context() && token.epoch === epoch },
    begin() { return { key: context(), revision: ++revision } },
    current(token) { return !disposed && token.key === context() && token.revision === revision },
    invalidate() { revision++; epoch++ },
    dispose() { disposed = true; revision++ },
  }
}
export function mergeDraft(draft, baseline, incoming) {
  return draft && JSON.stringify(draft) !== JSON.stringify(baseline) ? draft : { ...incoming }
}
