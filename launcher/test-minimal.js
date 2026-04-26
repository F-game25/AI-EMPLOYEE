console.log('Test started')
console.log('typeof require:', typeof require)
console.log('typeof module:', typeof module)

// Try old method
try {
  const electronPath = require('electron')
  console.log('require electron returned:', typeof electronPath, electronPath.substring(0, 80))
} catch(e) {
  console.log('require electron error:', e.message)
}

// Check if it's an app.asar issue
const fs = require('fs')
console.log('fs available: true')

console.log('Process info:')
console.log('process.type:', process.type)
console.log('process.argv:', process.argv)

process.exit(0)
