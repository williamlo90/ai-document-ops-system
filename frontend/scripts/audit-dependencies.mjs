import { execFileSync } from 'node:child_process'
import { readFileSync } from 'node:fs'

const allowlist = JSON.parse(
  readFileSync(new URL('../audit-allowlist.json', import.meta.url), 'utf8'),
)

const npmCli = process.env.npm_execpath
if (!npmCli) {
  throw new Error('Run this check through "npm run audit" so npm_execpath is available.')
}

const nodeExecutable = process.env.npm_node_execpath ?? process.execPath
let raw
try {
  raw = execFileSync(nodeExecutable, [npmCli, 'audit', '--json'], { encoding: 'utf8' })
} catch (error) {
  raw = error.stdout
}

if (!raw) {
  throw new Error('npm audit did not return a JSON report.')
}

const report = JSON.parse(raw)
const vulnerabilities = report.vulnerabilities ?? {}
const today = new Date().toISOString().slice(0, 10)
const failures = []
const accepted = []

for (const [packageName, vulnerability] of Object.entries(vulnerabilities)) {
  if (!['high', 'critical'].includes(vulnerability.severity)) continue
  const advisoryIds = collectAdvisoryIds(packageName, vulnerabilities)
  if (!advisoryIds.size) {
    failures.push(`${packageName}: ${vulnerability.severity} advisory has no reviewable ID`)
    continue
  }

  for (const advisoryId of advisoryIds) {
    const exception = allowlist.advisories.find((item) => item.id === advisoryId)
    if (!exception) {
      failures.push(`${packageName}: ${advisoryId} is not allowlisted`)
      continue
    }
    if (!exception.packages.includes(packageName)) {
      failures.push(`${packageName}: ${advisoryId} is allowlisted for different packages`)
      continue
    }
    if (exception.expires_on < today) {
      failures.push(`${packageName}: ${advisoryId} exception expired on ${exception.expires_on}`)
      continue
    }
    accepted.push(`${packageName}: ${advisoryId} accepted until ${exception.expires_on}`)
  }
}

if (accepted.length) {
  console.log('Reviewed temporary exceptions:')
  for (const item of accepted) console.log(`- ${item}`)
}

if (failures.length) {
  console.error('Unaccepted high/critical dependency findings:')
  for (const item of failures) console.error(`- ${item}`)
  process.exit(1)
}

console.log('No unaccepted high or critical npm advisories.')

function collectAdvisoryIds(packageName, allVulnerabilities, seen = new Set()) {
  if (seen.has(packageName)) return new Set()
  seen.add(packageName)
  const ids = new Set()
  for (const via of allVulnerabilities[packageName]?.via ?? []) {
    if (typeof via === 'string') {
      for (const inherited of collectAdvisoryIds(via, allVulnerabilities, seen)) {
        ids.add(inherited)
      }
      continue
    }
    const match = String(via.url ?? '').match(/GHSA-[\w-]+/)
    if (match) ids.add(match[0])
  }
  return ids
}
