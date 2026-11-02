// Run from the compiled Medusa server directory, after database migrations.
const requireFromApp = require('node:module').createRequire(require('node:path').join(process.cwd(), 'package.json'))
const { Client } = requireFromApp('pg')
const { spawnSync } = require('node:child_process')
async function main() {
  const email = process.env.BOOTSTRAP_ADMIN_EMAIL
  const password = process.env.BOOTSTRAP_ADMIN_PASSWORD
  if (!email || !password || password.length < 20) {
    throw new Error('Set BOOTSTRAP_ADMIN_EMAIL and a password of at least 20 characters')
  }
  const db = new Client({ connectionString: process.env.DATABASE_URL })
  await db.connect()
  try {
    const result = await db.query('SELECT id FROM "user" WHERE email = $1 AND deleted_at IS NULL LIMIT 1', [email])
    if (result.rows.length) {
      console.log('Administrator already provisioned')
      return
    }
  } finally {
    await db.end()
  }
  const result = spawnSync('../../../../node_modules/.bin/medusa', ['user', '-e', email, '-p', password], { encoding: 'utf8' })
  if (result.status !== 0) throw new Error('Administrator bootstrap failed; inspect configuration (credentials suppressed)')
  console.log('Administrator provisioned')
}
main().catch(error => { console.error(error.message); process.exit(1) })
