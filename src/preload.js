const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('mrAI', {
  speak: (text) => ipcRenderer.invoke('speak', text)
});
