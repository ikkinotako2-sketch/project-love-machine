import net from 'node:net';import http from 'node:http';import https from 'node:https';import {syncBuiltinESMExports} from 'node:module';
const stop=()=>{throw Error('OFFLINE_NETWORK_FORBIDDEN');};
globalThis.fetch=stop;net.connect=stop;net.createConnection=stop;net.Socket.prototype.connect=stop;http.request=stop;http.get=stop;https.request=stop;https.get=stop;syncBuiltinESMExports();
