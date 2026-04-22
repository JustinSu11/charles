const { contextBridge, ipcRenderer } = require('electron')

contextBridge.exposeInMainWorld('electronAPI', {
  start:       () => ipcRenderer.invoke('start-services'),
  stop:        () => ipcRenderer.invoke('stop-services'),
  interrupt:   () => ipcRenderer.invoke('interrupt-voice'),
  minimize:    () => ipcRenderer.invoke('minimize-window'),
  closeWindow: () => ipcRenderer.invoke('close-window'),
  quitApp:     () => ipcRenderer.invoke('quit-app'),
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
  onVoiceDebug: (cb) => {
    const listener = (_e, d) => cb(d)
    ipcRenderer.on('voice-debug', listener)
    return () => ipcRenderer.removeListener('voice-debug', listener)
  },
  getApiKeys:   () => ipcRenderer.invoke('settings:get-keys'),
  saveApiKeys:  (keys) => ipcRenderer.invoke('settings:save-keys', keys),
  getPrefs:     () => ipcRenderer.invoke('settings:get-prefs'),
  savePrefs:    (p)    => ipcRenderer.invoke('settings:save-prefs', p),
  installUpdate: () => ipcRenderer.invoke('install-update'),
  onUpdateStatus: (cb) => {
    const listener = (_e, d) => cb(d)
    ipcRenderer.on('update-status', listener)
    return () => ipcRenderer.removeListener('update-status', listener)
  },
})
