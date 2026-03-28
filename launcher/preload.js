const { contextBridge, ipcRenderer } = require('electron')

contextBridge.exposeInMainWorld('electronAPI', {
  start:          () => ipcRenderer.invoke('start-services'),
  stop:           () => ipcRenderer.invoke('stop-services'),
  minimize:       () => ipcRenderer.invoke('minimize-window'),
  closeWindow:    () => ipcRenderer.invoke('close-window'),
  onStatusUpdate: (cb) => ipcRenderer.on('status-update',      (_e, d) => cb(d)),
  onVoiceState:   (cb) => ipcRenderer.on('voice-state-update', (_e, d) => cb(d)),
})
