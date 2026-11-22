import { Pinecone } from "@pinecone-database/pinecone";

// Lazily create the client on first use. Instantiating at import time makes
// `next build` crash when PINECONE_API_KEY is not present in the build env.
let _client = null;
let _index = null;

function getClient() {
    if (!_client) {
        _client = new Pinecone({ apiKey: process.env.PINECONE_API_KEY });
    }
    return _client;
}

function getIndex() {
    if (!_index) _index = getClient().index('marketpulse');
    return _index;
}

// Same `index.query(...)` / `index.upsert(...)` / `index.namespace(...)` API as before.
export const index = new Proxy({}, {
    get(_target, prop) {
        const target = getIndex();
        const value = target[prop];
        return typeof value === 'function' ? value.bind(target) : value;
    }
});

export default new Proxy({}, {
    get(_target, prop) {
        const target = getClient();
        const value = target[prop];
        return typeof value === 'function' ? value.bind(target) : value;
    }
});
