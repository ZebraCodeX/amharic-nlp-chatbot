const { contextBridge } = require('electron');

// The API origin is passed from main via additionalArguments so the renderer
// (sandboxed, context-isolated) can point at the hosted Django backend.
const arg = process.argv.find((a) => a.startsWith('--hisar-api-base='));
const apiBase = arg ? arg.slice('--hisar-api-base='.length) : 'https://hisar-amharic-ai.fly.dev';

contextBridge.exposeInMainWorld('hisar', { apiBase });
