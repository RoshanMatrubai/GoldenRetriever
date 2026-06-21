import { io } from 'socket.io-client'

// Single socket shared across all components — vite proxies /socket.io → :5001
export const socket = io('/', {
  transports: ['polling', 'websocket'],
  reconnectionDelay: 1000,
  reconnectionAttempts: Infinity,
})
