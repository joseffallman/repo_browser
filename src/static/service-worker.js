// static/service-worker.js
self.addEventListener('install', event => {
    console.log('Service Worker installed.');
});

self.addEventListener('fetch', event => {
    // Låt bara alla nätverksförfrågningar gå vidare som vanligt.
});
