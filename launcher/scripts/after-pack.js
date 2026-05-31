/**
 * electron-builder afterPack hook.
 *
 * - Ensures bundled start.sh / stop.sh are executable in the packaged app.
 * - Logs the resource layout for verification.
 */
const fs = require('fs')
const path = require('path')

exports.default = async function afterPack(context) {
  const { appOutDir, packager } = context
  const resourcesDir =
    process.platform === 'darwin'
      ? path.join(appOutDir, `${packager.appInfo.productFilename}.app`, 'Contents', 'Resources')
      : path.join(appOutDir, 'resources')
  const repoDir = path.join(resourcesDir, 'repo')

  for (const name of ['start.sh', 'stop.sh']) {
    const file = path.join(repoDir, name)
    if (fs.existsSync(file)) {
      try {
        fs.chmodSync(file, 0o755)
        console.log(`[afterPack] chmod 755 ${file}`)
      } catch (e) {
        console.warn(`[afterPack] failed to chmod ${file}: ${e.message}`)
      }
    }
  }
}
