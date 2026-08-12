import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';

const CHARSET = 'qpzry9x8gf2tvdw0s3jn54khce6mua7l';
const MAP = new Map([...CHARSET].map((c, i) => [c, i]));
const HRP = 'age-secret-key-';
const INFO = Buffer.from('whatif-volcengine-image-runtime-auth-v1');

function polymod(values) {
  const GEN = [0x3b6a57b2, 0x26508e6d, 0x1ea119fa, 0x3d4233dd, 0x2a1462b3];
  let chk = 1;
  for (const v of values) {
    const top = chk >>> 25;
    chk = ((chk & 0x1ffffff) << 5) ^ v;
    for (let i = 0; i < 5; i++) if ((top >>> i) & 1) chk ^= GEN[i];
  }
  return chk >>> 0;
}
function hrpExpand(hrp) {
  return [...hrp].map(c => c.charCodeAt(0) >>> 5).concat([0], [...hrp].map(c => c.charCodeAt(0) & 31));
}
function convertBits(data, fromBits, toBits, pad = false) {
  let acc = 0, bits = 0;
  const ret = [], maxv = (1 << toBits) - 1;
  for (const value of data) {
    if (value < 0 || (value >>> fromBits)) throw new Error('BECH32_VALUE_RANGE');
    acc = (acc << fromBits) | value;
    bits += fromBits;
    while (bits >= toBits) {
      bits -= toBits;
      ret.push((acc >>> bits) & maxv);
    }
  }
  if (pad) {
    if (bits) ret.push((acc << (toBits - bits)) & maxv);
  } else if (bits >= fromBits || ((acc << (toBits - bits)) & maxv)) {
    throw new Error('BECH32_PADDING');
  }
  return Buffer.from(ret);
}
function decodeIdentity(secret) {
  const s = secret.trim().toLowerCase();
  const pos = s.lastIndexOf('1');
  if (pos <= 0) throw new Error('AGE_IDENTITY_INVALID');
  const hrp = s.slice(0, pos);
  const data = [...s.slice(pos + 1)].map(c => {
    if (!MAP.has(c)) throw new Error('AGE_IDENTITY_INVALID');
    return MAP.get(c);
  });
  if (polymod(hrpExpand(hrp).concat(data)) !== 1) throw new Error('AGE_IDENTITY_CHECKSUM');
  if (hrp !== HRP) throw new Error('AGE_IDENTITY_HRP');
  const raw = convertBits(data.slice(0, -6), 5, 8, false);
  if (raw.length !== 32) throw new Error('AGE_IDENTITY_LENGTH');
  return raw;
}
function identityFromFile(file) {
  const lines = fs.readFileSync(file, 'utf8').split(/\r?\n/).map(x => x.trim()).filter(Boolean);
  const secret = lines.find(x => x.startsWith('AGE-SECRET-KEY-'));
  if (!secret) throw new Error('AGE_IDENTITY_SECRET_MISSING');
  return decodeIdentity(secret);
}
function privateKeyFromRaw(raw) {
  const prefix = Buffer.from('302e020100300506032b656e04220420', 'hex');
  return crypto.createPrivateKey({key: Buffer.concat([prefix, raw]), format: 'der', type: 'pkcs8'});
}
function publicKeyFromRaw(raw) {
  const prefix = Buffer.from('302a300506032b656e032100', 'hex');
  return crypto.createPublicKey({key: Buffer.concat([prefix, raw]), format: 'der', type: 'spki'});
}

function main() {
  const [envelopePath, identityPath, outputPath] = process.argv.slice(2);
  if (!envelopePath || !identityPath || !outputPath) throw new Error('USAGE: envelope identity output');
  const env = JSON.parse(fs.readFileSync(envelopePath, 'utf8'));
  if (env.schema_version !== 1 || env.format !== 'whatif-x25519-hkdf-sha256-aes256gcm-v1') throw new Error('ENVELOPE_SCHEMA_INVALID');
  if (env.aad !== INFO.toString()) throw new Error('ENVELOPE_AAD_INVALID');
  const privateRaw = identityFromFile(identityPath);
  const privateKey = privateKeyFromRaw(privateRaw);
  const eph = publicKeyFromRaw(Buffer.from(env.ephemeral_public_key_b64, 'base64'));
  const shared = crypto.diffieHellman({privateKey, publicKey: eph});
  const salt = Buffer.from(env.salt_b64, 'base64');
  const nonce = Buffer.from(env.nonce_b64, 'base64');
  const sealed = Buffer.from(env.ciphertext_b64, 'base64');
  if (sealed.length < 17) throw new Error('ENVELOPE_CIPHERTEXT_INVALID');
  const ciphertext = sealed.subarray(0, sealed.length - 16);
  const tag = sealed.subarray(sealed.length - 16);
  const key = Buffer.from(crypto.hkdfSync('sha256', shared, salt, INFO, 32));
  const decipher = crypto.createDecipheriv('aes-256-gcm', key, nonce);
  decipher.setAAD(INFO);
  decipher.setAuthTag(tag);
  const plaintext = Buffer.concat([decipher.update(ciphertext), decipher.final()]);
  const payload = JSON.parse(plaintext.toString('utf8'));
  if (payload.schema_version !== 1 || !payload.access_key_id || !payload.secret_access_key) throw new Error('IMAGE_CREDENTIAL_PAYLOAD_INVALID');
  fs.mkdirSync(path.dirname(outputPath), {recursive: true, mode: 0o700});
  const tmp = `${outputPath}.tmp-${process.pid}`;
  fs.writeFileSync(tmp, `AccessKeyId: ${payload.access_key_id}\nSecretAccessKey: ${payload.secret_access_key}\n`, {mode: 0o600});
  fs.renameSync(tmp, outputPath);
  fs.chmodSync(outputPath, 0o600);
  process.stdout.write(JSON.stringify({status: 'PASS', credential_values_logged: false, output_materialized: true}) + '\n');
}

try { main(); } catch (err) {
  process.stderr.write(String(err?.message || err) + '\n');
  process.exit(2);
}
