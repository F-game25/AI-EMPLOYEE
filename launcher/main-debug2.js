console.log('process.versions:', JSON.stringify(process.versions, null, 2).slice(0, 200))
console.log('require.main === module:', require.main === module)
console.log('__dirname:', __dirname)
console.log('__filename:', __filename)

try {
  const mod = require.cache[require.resolve.paths('electron')[0] + '/electron']
  console.log('Cached electron:', mod)
} catch(e) {
  console.log('No cached electron')
}

// Try different approaches
try {
  const { remote } = require('electron')
  console.log('Got remote:', typeof remote)
} catch (e) {
  console.log('Error requiring remote:', e.message)
}

// Try preload environment variable
console.log('process.env.ELECTRON_PRELOAD:', process.env.ELECTRON_PRELOAD)

process.exit(0)
