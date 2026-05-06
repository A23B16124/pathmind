const CACHE = 'pathmind-v2'
const SHELL = ['/manifest.webmanifest']

self.addEventListener('install', (e) => {
  self.skipWaiting()
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(SHELL)).catch(() => {}))
})

self.addEventListener('activate', (e) => {
  e.waitUntil(
    caches.keys().then((keys) => Promise.all(keys.map((k) => caches.delete(k))))
  )
  self.clients.claim()
})

self.addEventListener('fetch', (e) => {
  const { request } = e
  if (request.method !== 'GET') return
  const url = new URL(request.url)

  if (
    url.pathname.startsWith('/api/') ||
    url.pathname.startsWith('/ws/') ||
    url.pathname.startsWith('/_next/')
  ) {
    return
  }

  if (url.pathname === '/' || url.pathname.startsWith('/report/')) {
    e.respondWith(fetch(request).catch(() => caches.match(request)))
    return
  }

  e.respondWith(
    caches.match(request).then((cached) => cached || fetch(request))
  )
})
