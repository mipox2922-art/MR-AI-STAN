# MR AI — Chief of Staff

MR AI ni desktop voice assistant ya Windows, iliyopangwa kuwa **voice-first** na kutumia Kiswahili.

## V1 scaffold
- Electron desktop app
- Safe `contextBridge` IPC
- Local text-to-speech kupitia `say`
- UI ya MR AI
- Mwanzo wa architecture ya voice assistant

## Mpango unaofuata
1. Wake word: **Hey Ferisi**
2. Speech-to-text ya Kiswahili
3. AI command router
4. Web research tools
5. Memory ya muda mrefu
6. Windows automation kwa actions salama
7. Installer ya Windows

## Run

```bash
npm install
npm start
```

> API keys na credentials hazipaswi kuwekwa kwenye GitHub. Tumia environment variables/local secret storage.
