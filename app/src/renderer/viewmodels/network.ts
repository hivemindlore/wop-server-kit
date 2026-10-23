import type { NetworkState } from '@shared/api'

export interface NetworkView {
  status: 'checking' | 'ok' | 'problems' | 'unknown'
  title: string
  problems: string[]
  canFix: boolean
  fixLabel: string
  fixing: boolean
  permissionHint: string
  notes: string[]
  others: string | null
  error: string | null
  helpUrl: string | null
}

/** "Can other computers find your server?" in words, for the Server tab and the setup. */
export function describeNetwork(state: NetworkState | null): NetworkView {
  const check = state?.check ?? null
  const busy = state?.busy ?? null
  let status: NetworkView['status'] = 'unknown'
  let title = 'Not checked yet.'
  if (busy === 'checking' || (!check && !state?.error)) {
    status = 'checking'
    title = 'Checking...'
  } else if (check && !check.checked) {
    title = `Couldn't read the ${check.firewall_name} settings. If others can't join, see the help page.`
  } else if (check?.ok) {
    status = 'ok'
    title = 'Yes! Other computers on your network can join.'
  } else if (check) {
    status = 'problems'
    title = 'Not yet: other computers on your network can\'t join.'
  }
  if (busy === 'fixing') title = 'Waiting for your permission...'
  const declined = check?.accepted === false && !check.ok
  return {
    status,
    title,
    problems: check?.problems.map((p) => p.text) ?? [],
    canFix: Boolean(check?.can_fix) && busy === null,
    fixLabel: busy === 'fixing' ? 'Fixing...' : 'Fix it',
    fixing: busy === 'fixing',
    permissionHint: declined
      ? 'Nothing was changed because permission wasn\'t given. Click "Fix it" to try again.'
      : (check?.permission_hint ?? ''),
    notes: check?.notes ?? [],
    others: check?.others.length
      ? `${check.others.join(', ')} also protects this computer. If players can't join, allow World of PADMAN there too.`
      : null,
    error: state?.error ?? null,
    helpUrl: check && !check.ok ? check.help_url : null
  }
}
