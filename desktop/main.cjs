const { app, BrowserWindow, Menu, shell } = require('electron');
const path = require('path');

const API_BASE = process.env.HISAR_API_BASE || 'https://hisar-amharic-ai.fly.dev';

/** The bundled SPA is shipped in resources/web (packaged) or ../frontend/dist (dev). */
function webRoot() {
  return app.isPackaged
    ? path.join(process.resourcesPath, 'web')
    : path.join(__dirname, '..', 'frontend', 'dist');
}

function createWindow() {
  const win = new BrowserWindow({
    width: 1120,
    height: 840,
    minWidth: 380,
    minHeight: 560,
    backgroundColor: '#f7f3e9',
    title: 'ሕሳር — Amharic AI',
    autoHideMenuBar: true,
    webPreferences: {
      preload: path.join(__dirname, 'preload.cjs'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: false,
      additionalArguments: [`--hisar-api-base=${API_BASE}`],
    },
  });

  // External links open in the user's browser, never inside the app.
  win.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url);
    return { action: 'deny' };
  });

  const devUrl = process.env.HISAR_DEV_URL;
  if (devUrl) {
    win.loadURL(devUrl);
  } else {
    win.loadFile(path.join(webRoot(), 'index.html'));
  }
}

function buildMenu() {
  const template = [
    {
      label: 'ሕሳር',
      submenu: [
        { role: 'about' },
        { type: 'separator' },
        { role: 'hide' },
        { role: 'quit' },
      ],
    },
    { role: 'editMenu' },
    {
      label: 'View',
      submenu: [
        { role: 'reload' },
        { role: 'zoomIn' },
        { role: 'zoomOut' },
        { role: 'resetZoom' },
        { type: 'separator' },
        { role: 'toggleDevTools' },
        { role: 'togglefullscreen' },
      ],
    },
    {
      role: 'help',
      submenu: [
        {
          label: 'GitHub',
          click: () => shell.openExternal('https://github.com/ZebraCodeX/amharic-nlp-chatbot'),
        },
        {
          label: 'Privacy',
          click: () => shell.openExternal(`${API_BASE}/privacy`),
        },
      ],
    },
  ];
  Menu.setApplicationMenu(Menu.buildFromTemplate(template));
}

const gotLock = app.requestSingleInstanceLock();
if (!gotLock) {
  app.quit();
} else {
  app.on('second-instance', () => {
    const win = BrowserWindow.getAllWindows()[0];
    if (win) {
      if (win.isMinimized()) win.restore();
      win.focus();
    }
  });
  app.whenReady().then(() => {
    buildMenu();
    createWindow();
    app.on('activate', () => {
      if (BrowserWindow.getAllWindows().length === 0) createWindow();
    });
  });
  app.on('window-all-closed', () => {
    if (process.platform !== 'darwin') app.quit();
  });
}
