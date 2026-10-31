function bytesToBase64(bytes) {
  let binary = '';
  for (const byte of new Uint8Array(bytes)) binary += String.fromCharCode(byte);
  return btoa(binary);
}

async function generateKeyPair() {
  const pair = await crypto.subtle.generateKey('Ed25519', true, ['sign', 'verify']);
  const [publicKey, privateKey] = await Promise.all([
    crypto.subtle.exportKey('raw', pair.publicKey),
    crypto.subtle.exportKey('pkcs8', pair.privateKey),
  ]);
  return {
    public_key: bytesToBase64(publicKey),
    private_key_pkcs8: bytesToBase64(privateKey),
  };
}

export async function generateDomainKeys(domain, members) {
  const users = [];
  for (const member of members) {
    const [intent, panic] = await Promise.all([generateKeyPair(), generateKeyPair()]);
    users.push({
      user_id: member.id,
      username: member.username,
      email: member.email,
      name: `${member.first_name} ${member.last_name}`,
      intent,
      panic,
    });
  }
  return {
    format: 'dns-intent-private-keys-v1',
    domain: domain.name,
    generated_at: new Date().toISOString(),
    warning: 'PRIVATE KEY MATERIAL — store securely and never upload this file.',
    users,
  };
}

export function publicKeysPayload(keyFile) {
  return keyFile.users.map((user) => ({
    user_id: user.user_id,
    intent_public_key: user.intent.public_key,
    panic_public_key: user.panic.public_key,
  }));
}

export function downloadPrivateKeys(keyFile) {
  const blob = new Blob([`${JSON.stringify(keyFile, null, 2)}\n`], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = `${keyFile.domain.replace(/[^a-z0-9.-]/gi, '_')}-private-keys.json`;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}
