// In Electron main process, we need to check what's available
console.log('Checking global scope...')
console.log('global.process:', typeof global.process)
console.log('global.require:', typeof global.require)

// Try accessing electron internals
console.log('\nChecking module.require...')
const testRequire = module.require
console.log('module.require:', typeof testRequire)

// In Electron, the electron module should be available in the asar
// Let's try to list what module actually loads
const moduleProto = Object.getPrototypeOf(module)
console.log('\nmodule methods:', Object.getOwnPropertyNames(moduleProto).slice(0, 10))

// Check if there's an electron exports anywhere
try {
  const electronPath = require.resolve('electron')
  console.log('Resolved electron path:', electronPath)
} catch(e) {
  console.log('Error resolving electron:', e.message)
}

// Try the Module.js approach
const Module = require('module')
console.log('\nModule._load:', typeof Module._load)

// Check if electron is available in electron's internal modules
const fs = require('fs')
console.log('fs available:', typeof fs === 'object')

//Try loading from dist
try {
  const electronBinary = require.resolve('electron')
  console.log('electron binary:', electronBinary)
} catch (e) {
  console.log('Cannot resolve electron')
}

process.exit(0)
