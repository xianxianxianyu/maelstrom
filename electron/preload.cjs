const { contextBridge } = require('electron');

contextBridge.exposeInMainWorld('maelstromDesktop', {
  platform: process.platform,
});
