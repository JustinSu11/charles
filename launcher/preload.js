const { contextBridge, ipcRenderer } = require('electron')

contextBridge.exposeInMainWorld('electronAPI', {
  start:       () => ipcRenderer.invoke('start-services'),
  stop:        () => ipcRenderer.invoke('stop-services'),
  minimize:    () => ipcRenderer.invoke('minimize-window'),
  closeWindow: () => ipcRenderer.invoke('close-window'),
  onStatusUpdate: (cb) => {
    const listener = (_e, d) => cb(d)
    ipcRenderer.on('status-update', listener)
    return () => ipcRenderer.removeListener('status-update', listener)
  },
  onVoiceState: (cb) => {
    const listener = (_e, d) => cb(d)
    ipcRenderer.on('voice-state-update', listener)
    return () => ipcRenderer.removeListener('voice-state-update', listener)
  },
  onVoiceTranscript: (cb) => {
    const listener = (_e, d) => cb(d)
    ipcRenderer.on('voice-transcript', listener)
    return () => ipcRenderer.removeListener('voice-transcript', listener)
  },
})
