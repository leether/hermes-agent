import { expect, test } from 'vitest'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { spawnSync } from 'node:child_process'
import { randomBytes } from 'node:crypto'
import { verifyBundleStamp, verifyMacMetadata } from '../tests/install/e2e-assets/bundle-smoke-metadata.mjs'
import { stampAssertions } from '../tests/install/e2e-assets/mac-bundled-manifest.cjs'
import { buildStampPayload } from '../apps/desktop/scripts/write-build-stamp.mjs'

const commit = 'a'.repeat(40)

// Validator calls launch Python too: keep each independent admission within its original cap.
function channelRequest() {
  const token = randomBytes(8).toString('hex'), sequence = 65537
  return { schema: 1, buildId: randomBytes(16).toString('hex'), channel: `smoke-${token}`,
    repository: 'NousResearch/hermes-agent', publicBase: 'https://releases.example.test', commit,
    sourceVersion: '1.2.3', sequence, version: `0.0.${sequence}`,
    windowsVersion: `0.${Math.floor(sequence / 65536)}.${sequence % 65536}.0`, bundleEnv: {},
    identity: { token, displayName: 'Smoke Channel', appId: `com.example.preview-${token}`,
      appNamePascal: `Smoke${token}`, artifactNamePascal: `Artifact${token}`,
      msixAppIdWithOrg: `Example.Smoke${token}`, cliName: `smoke-${token}`, windowsExecutableName: `smoke-${token}` } }
}

function withChannelRequest(body) {
  const temp = fs.mkdtempSync(path.join(os.tmpdir(), 'channel-smoke-'))
  const request = channelRequest()
  const cli = path.resolve(import.meta.dirname, '../tests/install/e2e-assets/bundle-smoke-metadata.mjs')
  const requestPath = path.join(temp, 'request.json'), stampPath = path.join(temp, 'stamp.json')
  const run = (command, args = []) => spawnSync(process.execPath,
    [cli, command, '--commit', commit, '--channel-request', requestPath, ...args], { encoding: 'utf8' })
  try {
    fs.writeFileSync(requestPath, JSON.stringify(request))
    return body({ request, requestPath, stampPath, run })
  } finally { fs.rmSync(temp, { recursive: true, force: true }) }
}

function withChannelStamp(platform, body) {
  return withChannelRequest(fixture => {
    const { request } = fixture
    const env = { ...process.env, HERMES_DESKTOP_VARIANT: 'bundled', HERMES_BUILD_COMMIT: '',
      HERMES_PAYLOAD_TAG: '', HERMES_PAYLOAD_VERSION: '', _HERMES_CHANNEL_REQUEST_JSON: JSON.stringify(request) }
    const stamp = buildStampPayload({ commit, dirty: false }, env, platform,
      { runtime: { commands: { hermes: 'bin/hermes' } } })
    return body({ ...fixture, stamp, options: { commit, platform, channelRequest: request } })
  })
}

function withMacMetadata(body) {
  return withChannelStamp('darwin', fixture => {
    const { request } = fixture
    const plist = { CFBundleIdentifier: request.identity.appId, CFBundleShortVersionString: request.version,
      CFBundleVersion: request.version, CFBundleExecutable: request.identity.displayName }
    return body({ ...fixture, plist })
  })
}

test('channel smoke identity binds the complete admitted request', () => {
  withChannelRequest(({ request, run }) => {
    const identity = run('identity')
    expect(identity.status, identity.stderr).toBe(0)
    expect(JSON.parse(identity.stdout)).toMatchObject({ appId: request.identity.appId,
      msixIdentity: request.identity.msixAppIdWithOrg, applicationId: request.identity.appNamePascal,
      windowsVersion: request.windowsVersion })
  })
}, 15_000)

const platforms = ['darwin', 'win32']
test.each(platforms)('channel smoke stamp binds the admitted platform (%s)', platform => {
  withChannelStamp(platform, ({ request, stampPath, run, stamp }) => {
    fs.writeFileSync(stampPath, JSON.stringify(stamp))
    const result = run('stamp', ['--platform', platform, '--stamp', stampPath])
    expect(result.status, result.stderr).toBe(0)
    expect(JSON.parse(result.stdout)).toBe(platform === 'darwin' ? request.version : request.windowsVersion)
  })
}, 15_000)

const requestFields = platforms.flatMap(platform => Object.keys(channelRequest()).map(key => [platform, key]))
test.each(requestFields)('channel smoke rejects altered admitted request %s/%s', (platform, key) => {
  withChannelStamp(platform, ({ request, stamp, options }) => {
    const changed = { ...stamp, channelBuild: { ...request, [key]: null } }
    expect(() => verifyBundleStamp(changed, options), key).toThrow('channelBuild')
  })
}, 15_000)

const conflictingFields = [['source', 'commit-build'], ['tag', 'v1.2.3'], ['branch', 'main'],
  ['dirty', true], ['updateMechanism', 'external'], ['displayVersion', ''], ['baseVersion', '']]
const conflictingStamps = platforms.flatMap(platform => conflictingFields.map(([key, value]) => [platform, key, value]))
test.each(conflictingStamps)('channel smoke rejects conflicting stamp %s/%s', (platform, key, original) => {
  withChannelStamp(platform, ({ request, stamp, options }) => {
    const value = ['displayVersion', 'baseVersion'].includes(key) ? request.version : original
    expect(() => verifyBundleStamp({ ...stamp, [key]: value }, options), key).toThrow(key)
  })
}, 15_000)

test.each(platforms)('channel smoke requires its admitted request (%s)', platform => {
  withChannelStamp(platform, ({ stamp }) => {
    expect(() => verifyBundleStamp(stamp, { commit, platform })).toThrow()
  })
}, 15_000)

test('channel smoke verifies independent Mac bundle metadata', () => {
  withMacMetadata(({ request, stamp, plist, options }) => {
    expect(verifyMacMetadata(plist, stamp, options)).toBe(request.version)
  })
}, 15_000)

test.each(['CFBundleIdentifier', 'CFBundleShortVersionString', 'CFBundleVersion'])('channel smoke rejects wrong Mac %s', key => {
  withMacMetadata(({ stamp, plist, options }) => {
    expect(() => verifyMacMetadata({ ...plist, [key]: 'wrong' }, stamp, options)).toThrow(key)
  })
}, 15_000)

test('channel smoke binds the independent stamp witness to the exact request', () => {
  withChannelStamp('darwin', ({ request, stamp }) => {
    expect(stampAssertions(stamp, { commit, tag: null, channelRequest: request })).toEqual([])
    expect(stampAssertions(stamp, { commit, tag: null }).join(';')).toContain('channelBuild')
    expect(stampAssertions({ ...stamp, channelBuild: { ...request, bundleEnv: { HERMES_MODEL: 'other' } } },
      { commit, tag: null, channelRequest: request }).join(';')).toContain('channelBuild')
  })
}, 15_000)

test('channel smoke rejects a conflicting release tag', () => {
  withChannelRequest(({ run }) => {
    expect(run('identity', ['--tag', 'v1.2.3']).status).not.toBe(0)
  })
}, 15_000)

test.each(['empty', 'duplicate'])('channel smoke rejects %s request JSON', kind => {
  withChannelRequest(({ request, requestPath, run }) => {
    const raw = kind === 'empty' ? '' : JSON.stringify(request).replace('{', '{"channel":"duplicate",')
    fs.writeFileSync(requestPath, raw)
    expect(run('identity').status).not.toBe(0)
  })
}, 15_000)

test.each(['commit', 'channel', 'windowsVersion', 'identity'])('channel smoke rejects invalid %s', field => {
  withChannelRequest(({ request, requestPath, run }) => {
    const invalid = {
      commit: { ...request, commit: 'b'.repeat(40) },
      channel: { ...request, channel: 'smoke/invalid' },
      windowsVersion: { ...request, windowsVersion: '1.2.3.0' },
      identity: { ...request, identity: { token: request.identity.token } },
    }[field]
    fs.writeFileSync(requestPath, JSON.stringify(invalid))
    expect(run('identity').status).not.toBe(0)
  })
}, 15_000)
