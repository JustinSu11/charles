const { contextBridge, ipcRenderer } = require('electron')

contextBridge.exposeInMainWorld('wizardAPI', {
  checkPython:          ()     => ipcRenderer.invoke('wizard:check-python'),
  installDeps:          ()     => ipcRenderer.invoke('wizard:install-deps'),
  startOpenRouterOAuth: ()     => ipcRenderer.invoke('wizard:start-openrouter-oauth'),
  validatePicovoice:    (key)  => ipcRenderer.invoke('wizard:validate-picovoice', { picovoiceKey: key }),
  saveKeys:             (keys) => ipcRenderer.invoke('wizard:save-keys', keys),
  finish:               ()     => ipcRenderer.invoke('wizard:finish'),
  close:                ()     => ipcRenderer.invoke('wizard:close'),

  onInstallProgress: (cb) => {
    const listener = (_, d) => cb(d)
    ipcRenderer.on('wizard:install-progress', listener)
    return () => ipcRenderer.removeListener('wizard:install-progress', listener)
  },

  openExternal: (url) => ipcRenderer.invoke('wizard:open-external', url),
})
